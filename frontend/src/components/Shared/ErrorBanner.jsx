export function ErrorBanner({ message, testId }) {
  if (!message) return null;
  return (
    <p className="text-sm text-rose-400" data-testid={testId}>{message}</p>
  );
}
