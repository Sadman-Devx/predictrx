/** The PredictRx logo mark (design/logo/logo.png): rounded square with a white wave. Colour comes from CSS (`color`). */
export function BrandMark({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      <rect width="40" height="40" rx="11" fill="currentColor" />
      <path
        d="M10.5 22.5c2.6-1.2 3.6-6.2 6.2-5.2s2.6 4.4 5.2 2.4 3.2-5.4 7.6-4.2"
        fill="none"
        stroke="#fff"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}