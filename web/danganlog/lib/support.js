// 広告(AdSense)と支援(Buy Me a Coffee)の設定を検証する。
// 値はビルド時の環境変数から渡す。形式が不正な値は「未設定」として扱い、推測で補わない。
const CLIENT = /^ca-pub-\d{10,20}$/;
const SLOT = /^\d{6,20}$/;
const BMC = /^https:\/\/(?:www\.)?buymeacoffee\.com\/[A-Za-z0-9_-]+\/?$/;
const EMAIL = /^[^\s@<>"]+@[^\s@<>"]+\.[^\s@<>"]+$/;

export function resolveSupport({ client = '', slot = '', bmc = '', preview = '', contact = '' } = {}) {
  const c = String(client).trim();
  const s = String(slot).trim();
  const adsense = CLIENT.test(c) ? c : '';
  const adSlot = SLOT.test(s) ? s : '';
  const coffee = BMC.test(String(bmc).trim()) ? String(bmc).trim() : '';
  const email = EMAIL.test(String(contact).trim()) ? String(contact).trim() : '';
  return {
    adsenseClient: adsense,
    adSlot,
    adsLive: Boolean(adsense && adSlot),
    adsPreview: String(preview) === 'true' && !(adsense && adSlot),
    coffeeUrl: coffee,
    contactEmail: email,
    // ads.txt は AdSense 公式の固定形式。パブリッシャーIDは ca-pub- を pub- にしたもの。
    adsTxt: adsense ? `google.com, ${adsense.replace(/^ca-/, '')}, DIRECT, f08c47fec0942fa0\n` : ''
  };
}

export const support = resolveSupport({
  client: process.env.NEXT_PUBLIC_ADSENSE_CLIENT,
  slot: process.env.NEXT_PUBLIC_ADSENSE_SLOT,
  bmc: process.env.NEXT_PUBLIC_BMC_URL,
  preview: process.env.NEXT_PUBLIC_ADSENSE_PREVIEW,
  contact: process.env.NEXT_PUBLIC_CONTACT_EMAIL
});
