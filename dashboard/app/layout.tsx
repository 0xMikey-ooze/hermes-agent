import type { Metadata } from 'next'
import './globals.css'
import Link from 'next/link'

export const metadata: Metadata = {
  title: 'Hermes Dashboard',
  description: 'Hermes Agent Control Panel',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-[#0a0a0f] text-gray-200">
        <nav className="border-b border-[#1e1e2e] bg-[#12121a] px-6 py-3 flex items-center gap-6">
          <Link href="/" className="text-violet-400 font-bold text-lg tracking-tight hover:text-violet-300">
            ⚡ Hermes
          </Link>
          <Link href="/" className="text-sm text-gray-400 hover:text-gray-200 transition-colors">
            Status
          </Link>
          <Link href="/repos" className="text-sm text-gray-400 hover:text-gray-200 transition-colors">
            Repos
          </Link>
          <Link href="/tasks" className="text-sm text-gray-400 hover:text-gray-200 transition-colors">
            Tasks
          </Link>
          <Link href="/skills" className="text-sm text-gray-400 hover:text-gray-200 transition-colors">
            Skills
          </Link>
        </nav>
        <main className="p-6">
          {children}
        </main>
      </body>
    </html>
  )
}
