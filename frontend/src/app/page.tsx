/**
 * Landing page — server component. Just redirects to /chat.
 * (We could add a marketing-style intro, but for the MVP the
 * useful thing is the chat itself.)
 */

import { redirect } from "next/navigation";

export default function Home() {
  redirect("/chat");
}
