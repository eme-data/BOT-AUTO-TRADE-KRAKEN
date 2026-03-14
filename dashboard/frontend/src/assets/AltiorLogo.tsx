export default function AltiorLogo({ size = 44, className = '' }: { size?: number; className?: string }) {
  const h = size
  const w = size
  return (
    <svg
      width={w}
      height={h}
      viewBox="0 0 120 120"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      {/* Mountain "A" shape */}
      <path
        d="M60 12 L92 88 L80 88 L68 62 L52 62 L40 88 L28 88 Z"
        fill="url(#altior-grad)"
        stroke="url(#altior-grad)"
        strokeWidth="1"
        strokeLinejoin="round"
      />
      {/* Crossbar */}
      <path
        d="M48 68 L72 68"
        stroke="url(#altior-grad)"
        strokeWidth="6"
        strokeLinecap="round"
      />
      {/* Upward arrow emerging from the peak */}
      <path
        d="M62 36 L78 16"
        stroke="url(#altior-grad)"
        strokeWidth="5"
        strokeLinecap="round"
      />
      {/* Arrowhead */}
      <path
        d="M78 16 L68 18 L76 26 Z"
        fill="url(#altior-grad)"
      />
      {/* Text "ALTIOR" below */}
      <text
        x="60"
        y="104"
        textAnchor="middle"
        fill="currentColor"
        fontSize="14"
        fontWeight="700"
        fontFamily="Inter, system-ui, sans-serif"
        letterSpacing="3"
      >
        ALTIOR
      </text>
      <defs>
        <linearGradient id="altior-grad" x1="30" y1="12" x2="90" y2="88" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#60A5FA" />
          <stop offset="100%" stopColor="#3B82F6" />
        </linearGradient>
      </defs>
    </svg>
  )
}
