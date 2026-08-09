interface LinkButtonProps {
  url: string;
  title?: string;
  className?: string;
}

export function LinkButton({
  url,
  title = "查看数据",
  className = "",
}: LinkButtonProps) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className={`inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-blue-700 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:outline-none ${className}`}
    >
      {title}
    </a>
  );
}
