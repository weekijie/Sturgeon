import type { Metadata } from "next";
import { Outfit } from "next/font/google";
import "./globals.css";

const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin"],
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
    <html lang="en" className="dark" data-theme="dark" suppressHydrationWarning>
      <body className={`${outfit.variable} font-sans bg-background text-foreground antialiased selection:bg-teal/30 relative`}>
        {/* Ambient Glow Background */}
        <div className="fixed inset-0 z-[-1] overflow-hidden pointer-events-none">
          <div className="absolute top-[-10%] right-[-5%] w-[500px] h-[500px] rounded-full bg-teal/10 blur-[100px]" />
          <div className="absolute bottom-[-10%] left-[-5%] w-[500px] h-[500px] rounded-full bg-accent/10 blur-[100px]" />
        </div>
        {children}
      </body>
    </html>
  );
}

