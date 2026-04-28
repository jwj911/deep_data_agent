import React from "react";

interface LogoProps {
  width?: number;
  height?: number;
  className?: string;
}

export const Logo: React.FC<LogoProps> = ({ width, height, className }) => {
  return (
    <img
      src="/data_copilot/logo.png"
      alt="Logo"
      className={`object-contain ${className || ""}`}
      style={{
        width: width || height ? 'auto' : undefined,
        height: width || height ? 'auto' : undefined,
        maxWidth: width || undefined,
        maxHeight: height || undefined,
      }}
    />
  );
};