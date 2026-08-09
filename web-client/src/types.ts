export type WorkspaceView = "translate" | "characters" | "context" | "pronouns" | "settings";
export type AiTaskKind = "translate" | "polish" | "pronouns" | "review";

export interface AiTaskSettings {
  model: string;
  maxOutputTokens: number | null;
  systemInstruction: string;
}

export interface Project {
  id: string;
  name: string;
  sourceLanguage: string;
  targetLanguage: string;
  characters: string;
  characterIndex?: number;
  characterBatchSize?: number;
  contextV1: string;
  promptRole?: string;
  promptTask?: string;
  polishPromptRole?: string;
  polishPromptTask?: string;
  glossaryIndex?: number;
  glossaryBatchSize?: number;
  styleNotes?: string;
  pronouns?: string;
  glossary?: Array<{ id: string; source: string; target: string }>;
  createdAt: string;
  updatedAt: string;
}

export interface Chapter {
  id: string;
  projectId: string;
  title: string;
  translatedTitle?: string;
  source: string;
  translation: string;
  review?: string;
  localFileName?: string;
  localReviewData?: Record<string, unknown>;
  localReviewText?: string;
  order: number;
  updatedAt: string;
}

export interface ProjectAsset {
  id: string;
  projectId: string;
  chapterId?: string;
  name: string;
  mimeType: string;
  blob: Blob;
  localPath?: string;
}

export interface AppSettings {
  id: "app";
  model: string;
  temperature: number;
  topP: number;
  topK: number;
  maxOutputTokens: number;
  tasks?: Record<AiTaskKind, AiTaskSettings>;
  rememberApiKey: boolean;
  apiKey?: string;
}
