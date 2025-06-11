import { NextRequest, NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';
import { spawn } from 'child_process';
import path from 'path';
import os from 'os';
import fs from 'fs/promises';

const prisma = new PrismaClient();

// Helper to parse multipart form data
const parseForm = async (req: NextRequest): Promise<{ fields: any; files: any }> => {
    const formData = await req.formData();
    const fields: { [key: string]: any } = {};
    const files: { [key: string]: any } = {};

    for (const [key, value] of formData.entries()) {
        if (typeof value === 'object' && 'name' in value) { // It's a file
            const file = value as File;
            const tempDir = path.join(os.tmpdir(), 'content-app-uploads');
            await fs.mkdir(tempDir, { recursive: true });
            const tempFilePath = path.join(tempDir, file.name);
            const buffer = Buffer.from(await file.arrayBuffer());
            await fs.writeFile(tempFilePath, buffer);
            files[key] = { filepath: tempFilePath, originalFilename: file.name };
        } else {
            fields[key] = value;
        }
    }
    return { fields, files };
};


export async function POST(req: NextRequest) {
    try {
        const { fields, files } = await parseForm(req);
        const { inputType, text, url } = fields;

        if (!inputType) {
            return NextResponse.json({ error: 'inputType is required' }, { status: 400 });
        }

        // 1. Create a Job in the database
        let inputDataValue = '';
        if (inputType === 'youtube') inputDataValue = url;
        if (inputType === 'text') inputDataValue = text.substring(0, 200);
        if (inputType === 'pdf') inputDataValue = files.pdfFile?.originalFilename || 'uploaded.pdf';

        const job = await prisma.job.create({
            data: {
                inputType,
                inputData: inputDataValue,
                status: 'processing',
            },
        });

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

        let scriptArgs: string[] = [];
        if (inputType === 'youtube') {
            scriptArgs = [inputType, url, job.id];
        } else if (inputType === 'pdf') {
            if (!files.pdfFile) {
                throw new Error("No PDF file uploaded");
            }
            scriptArgs = [inputType, files.pdfFile.filepath, job.id];
        } else if (inputType === 'text') {
            scriptArgs = [inputType, text, job.id];
        } else {
            throw new Error("Invalid input type");
        }

        const pythonProcess = spawn(venvPython, [pythonScriptPath, ...scriptArgs]);

        pythonProcess.on('error', async (err) => {
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
        });

        pythonProcess.stderr.on('data', (data) => {
            console.error(`Python Error: ${data}`);
            scriptError += data.toString();
        });

        pythonProcess.on('close', async (code) => {
            try {
                if (code === 0 && scriptOutput) {
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
                                mediaPath: post.media_path,
                                quoteSnippet: post.quote_snippet,
                                startTime: post.start_time,
                                endTime: post.end_time,
                                pageNumber: post.page_number,
                            })),
                        });
                    }
                } else {
                    // --- THIS IS THE CORRECTED ERROR HANDLING BLOCK ---
                    // Split the error output by lines and get the last non-empty line
                    const errorLines = scriptError.trim().split('\n');
                    const lastLine = errorLines[errorLines.length - 1];

                    let errorMessage = 'Unknown Python script error.';
                    try {
                        // Only try to parse the last line as JSON
                        const errorResult = JSON.parse(lastLine);
                        if (errorResult && errorResult.error) {
                            errorMessage = errorResult.error;
                        }
                    } catch (e) {
                        // If parsing fails, use the last line as a raw error message,
                        // or a snippet of the full error log.
                        errorMessage = lastLine || scriptError.substring(0, 500);
                    }

                    await prisma.job.update({
                        where: { id: job.id },
                        data: {
                            status: 'failed',
                            error: errorMessage,
                        },
                    });
                    // ----------------------------------------------------
                }
            } catch (dbError: any) {
                console.error("Database update error:", dbError);
                await prisma.job.update({
                    where: { id: job.id },
                    data: { status: 'failed', error: `Failed to process script output or update DB. ${dbError.message}` },
                });
            }

            // Clean up temp PDF file
            if (inputType === 'pdf' && files.pdfFile) {
                await fs.unlink(files.pdfFile.filepath);
            }
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
    const { searchParams } = new URL(req.url);
    const jobId = searchParams.get('jobId');

    if (!jobId) {
        return NextResponse.json({ error: 'jobId is required' }, { status: 400 });
    }

    const job = await prisma.job.findUnique({
        where: { id: jobId },
        include: { posts: true },
    });

    if (!job) {
        return NextResponse.json({ error: 'Job not found' }, { status: 404 });
    }

    return NextResponse.json(job);
}