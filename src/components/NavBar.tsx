'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

export function NavBar() {
  const pathname = usePathname();

  const linkClasses = (path: string) =>
    `px-3 py-2 rounded-md text-sm font-medium hover:text-blue-600 ${
      pathname === path ? 'text-blue-600 font-semibold' : 'text-gray-600 dark:text-gray-300'
    }`;

  return (
    <nav className="bg-white dark:bg-gray-800 shadow mb-6">
      <div className="container mx-auto px-4 py-3 flex items-center justify-between">
        <Link href="/" className="text-xl font-bold text-gray-900 dark:text-gray-100">
          Content Atomizer
        </Link>
        <div className="flex space-x-4">
          <Link href="/" className={linkClasses('/')}>Home</Link>
          <Link href="/history" className={linkClasses('/history')}>History</Link>
        </div>
      </div>
    </nav>
  );
}
