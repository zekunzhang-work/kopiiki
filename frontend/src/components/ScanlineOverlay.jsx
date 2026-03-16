export default function ScanlineOverlay({ active }) {
  if (!active) return null;

  return (
    <div className="scanline-overlay">
      <div className="scan-grid"></div>
      <div className="scanline"></div>
    </div>
  );
}
