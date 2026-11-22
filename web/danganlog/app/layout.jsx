import './globals.css';

export const metadata = {
  title: 'DANGAN LOG — Linux道場',
  description: '説明を読み、コマンドを入力して学ぶLinux道場。ブラウザーで基礎から自分のペースで練習できます。',
  metadataBase: new URL('https://danganlog.com')
};

export const viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#101c22' },
    { media: '(prefers-color-scheme: dark)', color: '#0d171c' }
  ]
};

export default function RootLayout({ children }) {
  return (
    <html lang="ja" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
