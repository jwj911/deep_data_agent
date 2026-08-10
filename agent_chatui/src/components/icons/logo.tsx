import Image from "next/image";
import React from "react";

interface LogoProps {
  width?: number;
  height?: number;
  className?: string;
}

export const Logo: React.FC<LogoProps> = ({ width, height, className }) => {
  const intrinsicWidth = width ?? height ?? 32;
  const intrinsicHeight = height ?? width ?? 32;

  return (
    <Image
      src="/data_copilot/logo.png"
      alt="Logo"
      width={intrinsicWidth}
      height={intrinsicHeight}
      className={`object-contain ${className || ""}`}
      style={{
        width: width || height ? "auto" : undefined,
        height: width || height ? "auto" : undefined,
        maxWidth: width || undefined,
        maxHeight: height || undefined,
      }}
    />
  );
};
