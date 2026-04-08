export function FNOConfluenceBar({ score, quality, variant = "default" }) {
  const label = variant === "top4" || variant === "stock" ? "Confidence" : "Confluence";
  const star = score >= 80 ? "* " : "";
  const suffix = variant === "top4" ? "" : variant === "stock" ? "" : ` (${quality})`;
  return (
    <p>{label}: {star}{score}{suffix}</p>
  );
}
