import type { Metadata } from "next";
import { Source_Sans_3, Source_Code_Pro } from "next/font/google";
import "./globals.css";
import { CaseProvider } from "./context/CaseContext";

const sourceSans = Source_Sans_3({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
});

const sourceCode = Source_Code_Pro({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Sturgeon | Diagnostic Debate AI",
  description: "House MD-style diagnostic debate AI powered by MedGemma. Upload lab reports, challenge the AI, and arrive at a diagnosis together.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${sourceSans.variable} ${sourceCode.variable} font-sans bg-background text-foreground antialiased selection:bg-teal-light`}>
        {/* Teal top bar (NIH-style) */}
        <div className="h-[3px] bg-teal w-full fixed top-0 z-[100]" />
        <CaseProvider>
          {children}
        </CaseProvider>
      </body>
    </html>
  );
}
