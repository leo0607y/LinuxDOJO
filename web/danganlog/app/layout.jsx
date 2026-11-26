import './globals.css';
import { support } from '../lib/support.js';

export const metadata = {
  title: 'DANGAN LOG — Linux道場',
  description: '説明を読み、コマンドを入力して学ぶLinux道場。ブラウザーで基礎から自分のペースで練習できます。',
  metadataBase: new URL('https://danganlog.com'),
  ...(support.adsenseClient ? { other: { 'google-adsense-account': support.adsenseClient } } : {})
};

export const viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#29252a'
};

export default function RootLayout({ children }) {
  return (
    <html lang="ja" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
