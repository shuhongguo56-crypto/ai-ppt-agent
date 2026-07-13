import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI PPT Agent",
  description: "中文 AI PPT SaaS：从资料生成可编辑 PPTX 和 HyperFrames 动态 HTML。",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
