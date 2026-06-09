/**
 * Root layout. Wraps every page in the AuthProvider so any
 * component can call useAuth() without prop-drilling.
 */

import type { ReactNode } from "react";
import { AuthProvider } from "@/components/Auth/AuthProvider";
import "./globals.css";

export const metadata = {
  title: "EduRag — NCERT Doubt Solver",
  description: "Class 7-9 PCM doubts answered, grounded in your textbook.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
