import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Forge · Design 911',
  description: 'Finds Design 911 parts without descriptions, verifies them by part number across the web, and writes the listing in house voice.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB">
      <body className="min-h-screen font-sans grid-bg">{children}</body>
    </html>
  );
}
