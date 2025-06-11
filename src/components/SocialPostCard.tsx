import { Post } from '@prisma/client';

export function SocialPostCard({ post }: { post: Post }) {
    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden my-4">
            <div className="p-4">
                <p className="text-gray-800 dark:text-gray-200 whitespace-pre-wrap">{post.content}</p>
            </div>
            {post.mediaPath && (
                <div className="bg-gray-100 dark:bg-gray-900 p-2">
                    {post.mediaPath.endsWith('.mp4') ? (
                        <video controls src={post.mediaPath} className="w-full rounded-md" />
                    ) : (
                        <img src={post.mediaPath} alt="Extracted from source" className="w-full rounded-md" />
                    )}
                </div>
            )}
            <div className="px-4 py-2 bg-gray-50 dark:bg-gray-700/50 text-xs text-gray-500 dark:text-gray-400">
                {post.startTime !== null && post.endTime !== null && (
                    <span>Source: {post.startTime.toFixed(1)}s - {post.endTime.toFixed(1)}s</span>
                )}
                {post.pageNumber !== null && (
                    <span>Source: Page {post.pageNumber}</span>
                )}
            </div>
        </div>
    );
}
