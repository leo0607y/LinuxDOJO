'use client';

import { useEffect, useRef, useState } from 'react';
import { support } from '../lib/support.js';

const { adsLive, adsPreview, adsenseClient, adSlot, coffeeUrl } = support;
const SCRIPT_ID = 'adsense-script';

function loadAdsense() {
  if (document.getElementById(SCRIPT_ID)) return;
  const script = document.createElement('script');
  script.id = SCRIPT_ID;
  script.async = true;
  script.crossOrigin = 'anonymous';
  script.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(adsenseClient)}`;
  document.head.appendChild(script);
}

function AdSlot() {
  const ref = useRef(null);
  const [hasConsentTool, setHasConsentTool] = useState(false);
  useEffect(() => {
    // 同意メッセージはGoogleのCMP(Privacy & messaging)が広告スクリプトと一緒に表示する。
    loadAdsense();
    // GoogleのCMPが読み込まれた場合だけ、同意の変更・撤回ボタンを出す。
    let tries = 0;
    const timer = setInterval(() => {
      if (window.googlefc || ++tries > 40) { clearInterval(timer); if (window.googlefc) setHasConsentTool(true); }
    }, 500);
    const el = ref.current;
    if (el && !el.dataset.requested) {
      el.dataset.requested = '1';
      try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch { /* 広告ブロッカー等。学習には影響しない */ }
    }
    return () => clearInterval(timer);
  }, []);
  const reopenConsent = () => {
    const fc = window.googlefc;
    if (fc?.callbackQueue) fc.callbackQueue.push({ CONSENT_DATA_READY: () => fc.showRevocationMessage?.() });
  };
  return (
    <div className="ad-unit">
      <span className="ad-label">広告</span>
      <ins ref={ref} className="adsbygoogle ad-slot" style={{ display: 'block' }}
        data-ad-client={adsenseClient} data-ad-slot={adSlot} data-ad-format="rectangle" data-full-width-responsive="false" />
      {hasConsentTool ? <button type="button" className="ad-consent" onClick={reopenConsent}>広告の同意設定</button> : null}
    </div>
  );
}

export default function SupportRail() {
  const [wide, setWide] = useState(false);

  useEffect(() => {
    const query = window.matchMedia('(min-width: 1280px) and (min-height: 800px)');
    const update = () => setWide(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  if (!wide || (!adsLive && !adsPreview && !coffeeUrl)) return null;

  return (
    <aside className="support-rail" aria-label="広告とサイトの支援">
      {coffeeUrl ? <a className="coffee-link" href={coffeeUrl} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M5 9h12v6a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4V9Z" />
          <path d="M17 10h1.5a2.5 2.5 0 0 1 0 5H17M4 21h15M8 5c1-1 1-2 0-3m5 3c1-1 1-2 0-3" />
        </svg>
        <span>作者にCoffeeを送る</span><span aria-hidden="true">↗</span>
      </a> : null}
      {adsLive ? <AdSlot /> : null}
      {adsPreview ? <div className="ad-unit">
        <span className="ad-label">広告</span>
        <div className="ad-placeholder">広告のイメージ 300x250<br />広告通信は発生しません</div>
      </div> : null}
    </aside>
  );
}
