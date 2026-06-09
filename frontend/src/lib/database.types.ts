/**
 * Supabase database types. This is a hand-rolled type matching the
 * schema in backend/ingestion/schema.sql. In a larger project you'd
 * generate this with `supabase gen types typescript`, but for an
 * MVP the manual version is clearer and one less build step.
 *
 * If the schema changes, update this file in the same PR.
 */

export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[];

export interface Database {
  public: {
    Tables: {
      chat_messages: {
        Row: {
          id: string;
          user_id: string;
          class_level: string | null;
          subject: string | null;
          chapter_key: string | null;
          query: string;
          answer: string;
          sources: Json | null;
          created_at: string;
        };
        Insert: {
          id?: string;
          user_id: string;
          class_level?: string | null;
          subject?: string | null;
          chapter_key?: string | null;
          query: string;
          answer: string;
          sources?: Json | null;
          created_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["chat_messages"]["Insert"]>;
      };
      parent_chunks: {
        Row: {
          id: string;
          chapter_key: string;
          content: string;
          token_count: number;
          content_type: string;
          page_start: number | null;
          page_end: number | null;
          metadata: Json | null;
          created_at: string;
        };
        Insert: {
          id: string;
          chapter_key: string;
          content: string;
          token_count: number;
          content_type: string;
          page_start?: number | null;
          page_end?: number | null;
          metadata?: Json | null;
          created_at?: string;
        };
        Update: Partial<Database["public"]["Tables"]["parent_chunks"]["Insert"]>;
      };
    };
    Views: { [k: string]: never };
    Functions: { [k: string]: never };
    Enums: { [k: string]: never };
  };
}
