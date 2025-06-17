'use client';

import { useState, FormEvent, useEffect, useRef } from 'react';
import { Job, Post } from '@prisma/client';

type ExtendedPost = Post & { quoteSnippet: string | null };
import { SocialPostCard } from '@/components/SocialPostCard';

type InputType = 'youtube' | 'pdf' | 'text';

export default function HomePage() {
    const [inputType, setInputType] = useState<InputType>('youtube');
    const [inputValue, setInputValue] = useState('');
    const [pdfFile, setPdfFile] = useState<File | null>(null);
    type ModelType = 'phi' | 'gemini';
    const [model, setModel] = useState<ModelType>('gemini');
    const [isLoading, setIsLoading] = useState(false);
    const [jobId, setJobId] = useState<string | null>(null);
    const [jobResult, setJobResult] = useState<(Job & { posts: ExtendedPost[] }) | null>(null);
    const [error, setError] = useState<string | null>(null);
    const pollInterval = useRef<NodeJS.Timeout | null>(null);

    const pollJobStatus = async (id: string) => {
        try {
            const res = await fetch(`/api/process?jobId=${id}`);
            const data: Job & { posts: ExtendedPost[] } = await res.json();
            
            if (data.status === 'complete' || data.status === 'failed') {
                setIsLoading(false);
                setJobResult(data);
                if (data.status === 'failed') {
                    setError(data.error || 'Processing failed.');
                }
                if (pollInterval.current) {
                    clearInterval(pollInterval.current);
                }
            }
        } catch (e) {
            setError('Failed to fetch job status.');
            setIsLoading(false);
            if (pollInterval.current) {
                clearInterval(pollInterval.current);
            }
        }
    };

    useEffect(() => {
        if (jobId && isLoading) {
            pollInterval.current = setInterval(() => {
                pollJobStatus(jobId);
            }, 3000);
        }
        return () => {
            if (pollInterval.current) {
                clearInterval(pollInterval.current);
            }
        };
    }, [jobId, isLoading]);

    const handleSubmit = async (e: FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError(null);
        setJobId(null);
        setJobResult(null);

        const formData = new FormData();
        formData.append('inputType', inputType);
        formData.append('llmModel', model);

        if (inputType === 'youtube') {
            formData.append('url', inputValue);
        } else if (inputType === 'text') {
            formData.append('text', inputValue);
        } else if (inputType === 'pdf' && pdfFile) {
            formData.append('pdfFile', pdfFile);
        } else {
            setError('Please provide valid input.');
            setIsLoading(false);
            return;
        }

        try {
            const res = await fetch('/api/process', {
                method: 'POST',
                body: formData,
            });

            if (res.status === 202) {
                const data = await res.json();
                setJobId(data.jobId);
            } else {
                const errData = await res.json();
                setError(errData.error || 'An unexpected error occurred.');
                setIsLoading(false);
            }
        } catch (e: any) {
            setError(e.message);
            setIsLoading(false);
        }
    };

    const renderInput = () => {
        switch (inputType) {
            case 'youtube':
                return <input type="url" value={inputValue} onChange={(e) => setInputValue(e.target.value)} placeholder="https://www.youtube.com/watch?v=..." className="w-full p-2 border rounded bg-gray-50 dark:bg-gray-700 dark:border-gray-600" />;
            case 'pdf':
                return <input type="file" accept=".pdf" onChange={(e) => setPdfFile(e.target.files ? e.target.files[0] : null)} className="w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100" />;
            case 'text':
                return <textarea value={inputValue} onChange={(e) => setInputValue(e.target.value)} placeholder="Paste your text here..." rows={8} className="w-full p-2 border rounded bg-gray-50 dark:bg-gray-700 dark:border-gray-600" />;
        }
    };

    return (
        <main className="container mx-auto p-4 md:p-8 font-sans bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100 min-h-screen">
            <header className="text-center mb-8">
                <h1 className="text-4xl font-bold">Content Atomizer</h1>
                <p className="text-lg text-gray-600 dark:text-gray-400 mt-2">Turn any content into social media gold.</p>
            </header>

            <div className="max-w-2xl mx-auto bg-white dark:bg-gray-800 p-6 rounded-lg shadow-lg">
                <form onSubmit={handleSubmit}>
                    <div className="mb-4">
                        <div className="flex border-b border-gray-200 dark:border-gray-700">
                            {(['youtube', 'pdf', 'text'] as InputType[]).map(type => (
                                <button key={type} type="button" onClick={() => { setInputType(type); setInputValue(''); setPdfFile(null); }} className={`capitalize px-4 py-2 -mb-px font-semibold ${inputType === type ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500'}`}>
                                    {type}
                                </button>
                            ))}
                        </div>
                    </div>
                    <div className="mb-4">{renderInput()}</div>
                    <div className="mb-4">
                        <label className="block mb-2 font-medium">Model</label>
                        <select
                            value={model}
                            onChange={(e) => setModel(e.target.value as ModelType)}
                            className="w-full p-2 border rounded bg-gray-50 dark:bg-gray-700 dark:border-gray-600"
                        >
                            <option value="phi">Phi 3.1 Mini (local)</option>
                            <option value="gemini">Gemini 2.5 Pro Preview (06-05)</option>
                        </select>
                    </div>
                    <button type="submit" disabled={isLoading} className="w-full bg-blue-600 text-white font-bold py-2 px-4 rounded hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center">
                        {isLoading ? (
                            <>
                                <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                Processing...
                            </>
                        ) : 'Atomize Content'}
                    </button>
                </form>
            </div>

            {error && <div className="max-w-2xl mx-auto mt-4 p-4 bg-red-100 text-red-800 border border-red-300 rounded-lg">{error}</div>}

            <div className="max-w-2xl mx-auto mt-8">
                {jobResult?.status === 'complete' && (
                    <div>
                        <h2 className="text-2xl font-bold mb-4">Generated Posts</h2>
                        {jobResult.posts.map(post => <SocialPostCard key={post.id} post={post} />)}
                    </div>
                )}
            </div>
        </main>
    );
}
