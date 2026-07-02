"use client";

/**
 * QueryInput — textarea + send button. Cmd/Ctrl+Enter to submit.
 * Disabled while a stream is in progress.
 */

import { useState, type FormEvent, type KeyboardEvent } from "react";

interface Props {
  onSubmit: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function QueryInput({ onSubmit, disabled, placeholder }: Props) {
  const [value, setValue] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!value.trim() || disabled) return;
    onSubmit(value);
    setValue("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Cmd+Enter (Mac) or Ctrl+Enter (Win/Linux) submits.
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit(e as unknown as FormEvent);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-1.5 sm:gap-2">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder ?? "Ask a question about your textbook…"}
        rows={2}
        disabled={disabled}
        className="flex-1 resize-none px-2.5 sm:px-3 py-2 sm:py-2.5 border border-gray-300 rounded-lg text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="px-2.5 sm:px-4 py-1.5 sm:py-2 bg-brand-600 text-white text-xs sm:text-sm font-medium rounded-lg hover:bg-brand-700 disabled:opacity-50 transition flex-shrink-0 whitespace-nowrap"
      >
        Send
      </button>
    </form>
  );
}
