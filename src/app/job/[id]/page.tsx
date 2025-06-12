import prisma from '@/lib/prisma';
import { notFound } from 'next/navigation';
import { SocialPostCard } from '@/components/SocialPostCard';
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
      <h1 className="text-3xl font-bold mb-4">Job Details</h1>
      <p className="mb-6">Status: <span className="capitalize">{job.status}</span></p>
      {job.status === 'failed' && job.error && (
        <div className="mb-6 p-4 bg-red-100 text-red-800 border border-red-300 rounded-lg">{job.error}</div>
      )}
      {job.posts.length > 0 ? (
        job.posts.map(post => <SocialPostCard key={post.id} post={post as ExtendedPost} />)
      ) : (
        <p>No posts generated.</p>
      )}
    </main>
  );
}
