import prisma from '@/lib/prisma';
import Link from 'next/link';

export default async function HistoryPage() {
  const jobs = await prisma.job.findMany({
    orderBy: { createdAt: 'desc' },
  });

  return (
    <main className="container mx-auto p-4 md:p-8 font-sans bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100 min-h-screen">
      <h1 className="text-3xl font-bold mb-6">Job History</h1>
      <div className="overflow-x-auto">
        <table className="min-w-full bg-white dark:bg-gray-800 rounded-lg shadow">
          <thead>
            <tr>
              <th className="px-4 py-2 text-left">Created</th>
              <th className="px-4 py-2 text-left">Input</th>
              <th className="px-4 py-2 text-left">Status</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map(job => (
              <tr key={job.id} className="border-t border-gray-200 dark:border-gray-700">
                <td className="px-4 py-2 whitespace-nowrap">{job.createdAt.toLocaleString()}</td>
                <td className="px-4 py-2 capitalize">{job.inputType}</td>
                <td className="px-4 py-2 capitalize">{job.status}</td>
                <td className="px-4 py-2 text-right">
                  <Link href={`/job/${job.id}`} className="text-blue-600 hover:underline">View Posts</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
