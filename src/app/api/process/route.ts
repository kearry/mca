import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/prisma';
import { spawn } from 'child_process';
import path from 'path';
import { isPdfFile } from '@/lib/isPdfFile';
import os from 'os';
import fs from 'fs/promises';
import fsSync from 'fs';
import crypto from 'crypto';

// Job timeout: 30 minutes
const JOB_TIMEOUT = 30 * 60 * 1000;

// Helper to parse multipart form data
const parseForm = async (
    req: NextRequest
): Promise<{ fields: any; files: any; tempDir: string }> => {
    const formData = await req.formData();
    const fields: { [key: string]: any } = {};
    const files: { [key: string]: any } = {};

    // Create a unique temporary directory for this request
    const tempDir = await fs.mkdtemp(
        path.join(os.tmpdir(), 'content-app-uploads-')
    );

    for (const [key, value] of formData.entries()) {
        if (typeof value === 'object' && 'name' in value) {
            // It's a file
            const file = value as File;
            const safeName = path.basename(file.name);
            const tempFilePath = path.join(tempDir, safeName);
            const buffer = Buffer.from(await file.arrayBuffer());
            await fs.writeFile(tempFilePath, buffer);
            files[key] = {
                filepath: tempFilePath,
                originalFilename: safeName,
                mimetype: file.type || ''
            };
        } else {
            fields[key] = value;
        }
    }

    return { fields, files, tempDir };
};

// Helper used by tests and the close handler to build a final error message
// from the script's stderr output. When the exit code is non-zero the code is
// appended to the error string.
export const buildErrorMessage = (
    scriptError: string,
    code: number | null
): string => {
    const errorLines = scriptError.trim().split('\n');
    const lastLine = errorLines[errorLines.length - 1];

    let errorMessage = 'Unknown Python script error.';
    try {
        const errorResult = JSON.parse(lastLine);
        if (errorResult && (errorResult as any).error) {
            errorMessage = (errorResult as any).error;
        }
    } catch (e) {
        errorMessage = lastLine || scriptError.substring(0, 500);
    }

    if (code && code !== 0) {
        errorMessage += ` (exit code: ${code})`;
    }
    return errorMessage;
};

async function checkForTimedOutJobs() {
    // Check for and mark timed-out jobs as failed.
    try {
        const cutoff = new Date(Date.now() - JOB_TIMEOUT);
        const timedOutJobs = await prisma.job.findMany({
            where: {
                status: 'processing',
                createdAt: { lt: cutoff }
            }
        });

        if (timedOutJobs.length > 0) {
            await prisma.job.updateMany({
                where: {
                    id: { in: timedOutJobs.map(job => job.id) }
                },
                data: {
                    status: 'failed',
                    error: 'Job timed out after 30 minutes'
                }
            });
            console.log(`Marked ${timedOutJobs.length} jobs as timed out`);
        }
    } catch (error) {
        console.error('Error checking for timed out jobs:', error);
    }
}

export async function POST(req: NextRequest) {
    try {
        console.log('POST /api/process received');

        // Check for timed out jobs periodically
        await checkForTimedOutJobs();

        const { fields, files, tempDir } = await parseForm(req);
        console.log('Form fields:', fields);
        const { inputType, text, url, llmModel } = fields;

        if (!inputType) {
            return NextResponse.json({ error: 'inputType is required' }, { status: 400 });
        }

        if (inputType === 'pdf') {
            const uploaded = files.pdfFile;
            const isPdf = uploaded && isPdfFile(uploaded.originalFilename, uploaded.mimetype);
            if (!isPdf) {
                await fs.rm(tempDir, { recursive: true, force: true });
                return NextResponse.json({ error: 'Only PDF uploads are allowed' }, { status: 400 });
            }
        }

        // 1. Determine input identifier and checksum then check for existing completed job
        let inputDataValue = '';
        if (inputType === 'youtube') inputDataValue = url;
        if (inputType === 'text') inputDataValue = text.substring(0, 200);
        if (inputType === 'pdf') inputDataValue = files.pdfFile?.originalFilename || 'uploaded.pdf';

        let inputChecksum = '';
        if (inputType === 'youtube') {
            inputChecksum = crypto.createHash('sha256').update(url).digest('hex');
        } else if (inputType === 'text') {
            inputChecksum = crypto.createHash('sha256').update(text).digest('hex');
        } else if (inputType === 'pdf') {
            const buffer = fsSync.readFileSync(files.pdfFile.filepath);
            inputChecksum = crypto.createHash('sha256').update(buffer).digest('hex');
        }

        const existing = await prisma.job.findFirst({
            where: { inputType, inputChecksum, status: 'complete' },
            select: { id: true },
        });

        if (existing) {
            // Reuse previously generated results
            await fs.rm(tempDir, { recursive: true, force: true });
            return NextResponse.json({ jobId: existing.id }, { status: 200 });
        }

        const job = await prisma.job.create({
            data: {
                inputType,
                inputData: inputDataValue,
                inputChecksum,
                status: 'processing',
            },
        });
        console.log('Created job', job.id);

        // 2. Prepare and run the Python script
        const pythonScriptPath = path.resolve(process.cwd(), 'scripts/main.py');
        const venvPython = path.resolve(process.cwd(), 'venv/bin/python');

        try {
            await fs.access(venvPython);
        } catch {
            await prisma.job.update({
                where: { id: job.id },
                data: { status: 'failed', error: 'Python runtime not found' },
            });
            return NextResponse.json({ error: 'Python runtime not found' }, { status: 500 });
        }

        const model = llmModel || 'phi';
        let scriptArgs: string[] = [];
        if (inputType === 'youtube') {
            scriptArgs = [inputType, url, job.id, model];
        } else if (inputType === 'pdf') {
            if (!files.pdfFile) {
                throw new Error("No PDF file uploaded");
            }
            scriptArgs = [inputType, files.pdfFile.filepath, job.id, model];
        } else if (inputType === 'text') {
            const textPath = path.join(tempDir, 'input.txt');
            await fs.writeFile(textPath, text);
            scriptArgs = [inputType, textPath, job.id, model];
        } else {
            throw new Error("Invalid input type");
        }

        console.log('Running script', pythonScriptPath, scriptArgs.join(' '));
        const pythonProcess = spawn(venvPython, [pythonScriptPath, ...scriptArgs]);

        // Set a timeout for the Python process
        const processTimeout = setTimeout(() => {
            console.log('Python process timed out, killing...');
            pythonProcess.kill('SIGTERM');
        }, JOB_TIMEOUT);

        pythonProcess.on('error', async (err) => {
            clearTimeout(processTimeout);
            console.error('Failed to start Python process:', err);
            await prisma.job.update({
                where: { id: job.id },
                data: { status: 'failed', error: `Python process error: ${err.message}` },
            });
        });

        let scriptOutput = '';
        let scriptError = '';

        pythonProcess.stdout.on('data', (data) => {
            scriptOutput += data.toString();
            console.log('python stdout:', data.toString());
        });

        pythonProcess.stderr.on('data', (data) => {
            console.error(`Python Error: ${data}`);
            scriptError += data.toString();
        });

        pythonProcess.on('close', async (code, signal) => {
            clearTimeout(processTimeout);
            console.log('Python process exited with code', code, 'signal', signal);

            try {
                if (signal === 'SIGTERM') {
                    // Process was killed due to timeout
                    await prisma.job.update({
                        where: { id: job.id },
                        data: {
                            status: 'failed',
                            error: 'Job timed out after 30 minutes'
                        },
                    });
                } else if (code === 0 && scriptOutput) {
                    const result = JSON.parse(scriptOutput);
                    await prisma.job.update({
                        where: { id: job.id },
                        data: { status: 'complete' },
                    });

                    if (result.posts && Array.isArray(result.posts)) {
                        await prisma.post.createMany({
                            data: result.posts.map((post: any) => ({
                                jobId: job.id,
                                content: post.post_text,
                                quoteSnippet: post.source_quote,
                                pageNumber: post.page_number,
                            })),
                        });
                    }
                } else {
                    const errorMessage = buildErrorMessage(scriptError, code);
                    await prisma.job.update({
                        where: { id: job.id },
                        data: {
                            status: 'failed',
                            error: errorMessage,
                        },
                    });
                }
            } catch (dbError: any) {
                console.error("Database update error:", dbError);
                await prisma.job.update({
                    where: { id: job.id },
                    data: { status: 'failed', error: `Failed to process script output or update DB. ${dbError.message}` },
                });
            }

            // Clean up temporary directory and files
            await fs.rm(tempDir, { recursive: true, force: true });
        });

        // 3. Immediately return the Job ID to the frontend
        return NextResponse.json({ jobId: job.id }, { status: 202 });

    } catch (error: any) {
        console.error('API Error:', error);
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}

// GET endpoint to poll for job status
export async function GET(req: NextRequest) {
    console.log('GET /api/process');
    const { searchParams } = new URL(req.url);
    const jobId = searchParams.get('jobId');

    if (!jobId) {
        return NextResponse.json({ error: 'jobId is required' }, { status: 400 });
    }

    // Check for timed out jobs when polling
    await checkForTimedOutJobs();

    const job = await prisma.job.findUnique({
        where: { id: jobId },
        include: { posts: true },
    });

    if (!job) {
        console.log('Job not found', jobId);
        return NextResponse.json({ error: 'Job not found' }, { status: 404 });
    }

    return NextResponse.json(job);
}