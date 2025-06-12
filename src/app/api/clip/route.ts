import { NextRequest, NextResponse } from 'next/server';
import prisma from '@/lib/prisma';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs/promises';

export async function POST(req: NextRequest) {
  const { postId } = await req.json();

  if (!postId) {
    return NextResponse.json({ error: 'postId is required' }, { status: 400 });
  }

  const post = await prisma.post.findUnique({
    where: { id: postId },
    include: { job: true },
  });

  if (!post) {
    return NextResponse.json({ error: 'Post not found' }, { status: 404 });
  }

  if (post.mediaPath) {
    return NextResponse.json(post);
  }

  const pythonScriptPath = path.resolve(process.cwd(), 'scripts/main.py');
  const venvPython = path.resolve(process.cwd(), 'venv/bin/python');

  try {
    await fs.access(venvPython);
  } catch {
    return NextResponse.json({ error: 'Python runtime not found' }, { status: 500 });
  }

  const scriptArgs = ['clip', post.jobId, post.id, post.quoteSnippet || ''];

  return new Promise<NextResponse>(resolve => {
    const pythonProcess = spawn(venvPython, [pythonScriptPath, ...scriptArgs]);
    let output = '';
    let error = '';

    pythonProcess.stdout.on('data', (d) => {
      output += d.toString();
    });
    pythonProcess.stderr.on('data', (d) => {
      console.error('Python Error:', d.toString());
      error += d.toString();
    });
    pythonProcess.on('close', async (code) => {
      if (code === 0 && output) {
        try {
          const result = JSON.parse(output);
          const updated = await prisma.post.update({
            where: { id: post.id },
            data: {
              mediaPath: result.media_path,
              quoteSnippet: result.quote_snippet ?? post.quoteSnippet,
              startTime: result.start_time,
              endTime: result.end_time,
            },
          });
          resolve(NextResponse.json(updated));
        } catch (e: any) {
          resolve(NextResponse.json({ error: e.message }, { status: 500 }));
        }
      } else {
        resolve(
          NextResponse.json({ error: error.trim() || 'Clip extraction failed' }, { status: 500 })
        );
      }
    });
  });
}
