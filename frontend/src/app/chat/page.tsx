/**
 * /chat — the main page. Just renders the ChatWindow. The auth
 * gate (redirect to /login if not signed in) is intentionally
 * lax for the MVP — anonymous users can ask questions, they just
 * don't get history across devices.
 */

import { ChatWindow } from "@/components/Chat/ChatWindow";

export default function ChatPage() {
  return <ChatWindow />;
}
