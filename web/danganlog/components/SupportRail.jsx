'use client';

import { useEffect, useState } from 'react';

const previewAd = process.env.NEXT_PUBLIC_ADSENSE_PREVIEW === 'true';
const coffeeUrl = process.env.NEXT_PUBLIC_BMC_URL || '';

export default function SupportRail() {
  const [wide, setWide] = useState(false);

  useEffect(() => {
    const query = window.matchMedia('(min-width: 1280px) and (min-height: 800px)');
    const update = () => setWide(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  const coffee = /^https:\/\/(?:www\.)?buymeacoffee\.com\/[A-Za-z0-9_-]+\/?$/.test(coffeeUrl);
  if (!wide || (!previewAd && !coffee)) return null;

  return (
    <aside className="support-rail" aria-label="広告とサイトの支援">
      {previewAd ? <div className="ad-unit">
        <span className="ad-label">広告</span>
        <div className="ad-placeholder">AdSense枠のプレビュー<br />広告通信は発生しません</div>
      </div> : null}
      {coffee ? <a className="coffee-link" href={coffeeUrl} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">
        ☕ Coffeeで応援する ↗
      </a> : null}
    </aside>
  );
}
