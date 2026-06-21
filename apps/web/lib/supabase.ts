import { createClient } from "@supabase/supabase-js";

type ImportMetaWithEnv = ImportMeta & {
  env?: Record<string, string | undefined>;
};

const env = (import.meta as ImportMetaWithEnv).env ?? {};

const supabaseUrl = env.NEXT_PUBLIC_SUPABASE_URL ?? env.VITE_SUPABASE_URL;
const supabaseAnonKey =
  env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? env.VITE_SUPABASE_ANON_KEY;
const supabaseProjectUrl = supabaseUrl?.replace(/\/rest\/v1\/?$/, "");

export const supabase =
  supabaseProjectUrl && supabaseAnonKey ? createClient(supabaseProjectUrl, supabaseAnonKey) : null;
