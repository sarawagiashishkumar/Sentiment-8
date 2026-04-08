export function SectionHeader({ title, children, className = "" }) {
  return (
    <div className={`flex flex-row flex-wrap items-center justify-between gap-3 space-y-0 ${className}`}>
      <h2 className="text-lg font-bold text-white">{title}</h2>
      {children}
    </div>
  );
}
