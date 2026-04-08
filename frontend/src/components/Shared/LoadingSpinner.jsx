import { RefreshCw } from "lucide-react";

export function LoadingSpinner({ message = "Loading...", className = "" }) {
  return (
    <div className={`flex items-center gap-2 py-8 text-slate-400 ${className}`}>
      <RefreshCw size={20} className="animate-spin" />
      <span>{message}</span>
    </div>
  );
}
