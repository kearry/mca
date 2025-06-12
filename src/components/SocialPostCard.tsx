"use client";

import { Post } from '@prisma/client';
import Image from 'next/image';
import { useState } from 'react';

type ExtendedPost = Post & { quoteSnippet: string | null };

export function SocialPostCard({ post: initialPost }: { post: ExtendedPost }) {
    const [post, setPost] = useState(initialPost);
    const [loading, setLoading] = useState(false);

    const handleFindClip = async () => {
        setLoading(true);
        try {
            const res = await fetch('/api/clip', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ postId: post.id }),
            });
            if (res.ok) {
                const data = await res.json();
                setPost(data);
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden my-4">
            <div className="p-4">
                <p className="text-gray-800 dark:text-gray-200 whitespace-pre-wrap">{post.content}</p>
                {post.quoteSnippet && (
                    <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">&ldquo;{post.quoteSnippet}&rdquo;</p>
                )}
            </div>
            {post.mediaPath ? (
                <div className="bg-gray-100 dark:bg-gray-900 p-2">
                    {post.mediaPath.endsWith('.mp4') ? (
                        <video controls src={post.mediaPath} className="w-full rounded-md" />
                    ) : (
                        <Image
                            src={post.mediaPath}
                            alt="Extracted from source"
                            width={800}
                            height={600}
                            className="w-full rounded-md"
                        />
                    )}
                </div>
            ) : (
                <div className="p-4">
                    <button
                        onClick={handleFindClip}
                        disabled={loading}
                        className="bg-blue-600 text-white font-bold py-2 px-4 rounded hover:bg-blue-700 disabled:bg-gray-400"
                    >
                        {loading ? 'Searching...' : 'Find Clip'}
                    </button>
                </div>
            )}
            <div className="px-4 py-2 bg-gray-50 dark:bg-gray-700/50 text-xs text-gray-500 dark:text-gray-400">
                {post.startTime !== null && post.endTime !== null && (
                    <span>Source: {post.startTime.toFixed(1)}s - {post.endTime.toFixed(1)}s</span>
                )}
                {post.pageNumber !== null && <span>Source: Page {post.pageNumber}</span>}
            </div>
        </div>
    );
}
