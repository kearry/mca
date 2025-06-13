import prisma from '@/lib/prisma';
import { notFound } from 'next/navigation';
import { SocialPostCard } from '@/components/SocialPostCard';
import { TranscriptViewer } from '@/components/TranscriptViewer';
import { Post } from '@prisma/client';

type ExtendedPost = Post & { quoteSnippet: string | null };

export default async function JobPage({ params }: { params: { id: string } }) {
  const job = await prisma.job.findUnique({
    where: { id: params.id },
    include: { posts: true },
  });

  if (!job) {
    return notFound();
  }

  return (
    <main className="container mx-auto p-4 md:p-8 font-sans bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100 min-h-screen">
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Job Details</h1>
        <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
          <span>Type: <span className="capitalize">{job.inputType}</span></span>
          <span>Status: <span className="capitalize">{job.status}</span></span>
          <span>Created: {job.createdAt.toLocaleString()}</span>
        </div>
        <div className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          Input: {job.inputData}
        </div>
      </div>

      {job.status === 'failed' && job.error && (
        <div className="mb-6 p-4 bg-red-100 text-red-800 border border-red-300 rounded-lg">
          <strong>Error:</strong> {job.error}
        </div>
      )}

      {/* Show transcript if available */}
      {job.transcript && (
        <TranscriptViewer
          transcript={job.transcript}
          inputType={job.inputType}
        />
      )}

      {/* Show posts */}
      <div className="mb-6">
        <h2 className="text-2xl font-bold mb-4">Generated Posts ({job.posts.length})</h2>
        {job.posts.length > 0 ? (
          <div className="space-y-4">
            {job.posts.map(post => (
              <SocialPostCard key={post.id} post={post as ExtendedPost} />
            ))}
          </div>
        ) : (
          <p className="text-gray-500 dark:text-gray-400">No posts generated yet.</p>
        )}
      </div>
    </main>
  );
}