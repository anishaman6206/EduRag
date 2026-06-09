"use client";

/**
 * SubjectClassFilter — two dropdowns. The user picks a class and
 * (optionally) a subject. The values flow up to the chat window
 * and get sent as the body of the /ask request.
 *
 * "All" for subject is a special value that means "let the
 * classifier decide". The backend treats it as no filter.
 */

import type { ClassLevel, Subject } from "@/lib/types";

interface Props {
  classLevel: ClassLevel | "";
  subject: Subject | "" | "all";
  onChange: (next: { classLevel: ClassLevel | ""; subject: Subject | "" | "all" }) => void;
  disabled?: boolean;
}

export function SubjectClassFilter({ classLevel, subject, onChange, disabled }: Props) {
  return (
    <div className="flex items-center gap-2">
      <select
        aria-label="Class"
        value={classLevel}
        onChange={(e) => onChange({ classLevel: e.target.value as ClassLevel | "", subject })}
        disabled={disabled}
        className="text-sm border border-gray-300 rounded-md px-2 py-1 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
      >
        <option value="">Any class</option>
        <option value="7">Class 7</option>
        <option value="8">Class 8</option>
        <option value="9">Class 9</option>
        <option value="10">Class 10</option>
      </select>

      <select
        aria-label="Subject"
        value={subject}
        onChange={(e) => onChange({ classLevel, subject: e.target.value as Subject | "" | "all" })}
        disabled={disabled}
        className="text-sm border border-gray-300 rounded-md px-2 py-1 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
      >
        <option value="all">All subjects</option>
        <option value="math">Math</option>
        <option value="physics">Physics</option>
        <option value="chemistry">Chemistry</option>
      </select>
    </div>
  );
}
