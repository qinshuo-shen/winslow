import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { apiGet, ApiError } from "../api/client";
import type { CharacterOut } from "../api/types";

// Minimal shared state for the Character/Armory panels (Phase 3). Both
// panels care about the character's current Runes/level: CharacterPanel
// displays it directly, ArmoryPanel needs it to feel "live" after a
// purchase even though the server already computes each gear item's
// can_buy flag (a purchase spends Runes, which is state Armory doesn't
// otherwise refetch on its own). Plain useState/useEffect, no external
// state library -- this app doesn't need one at this size.

interface AppDataContextValue {
  character: CharacterOut | null;
  characterError: string | null;
  refetchCharacter: () => Promise<void>;
}

const AppDataContext = createContext<AppDataContextValue | null>(null);

export function AppDataProvider({ children }: { children: ReactNode }) {
  const [character, setCharacter] = useState<CharacterOut | null>(null);
  const [characterError, setCharacterError] = useState<string | null>(null);

  const refetchCharacter = useCallback(async () => {
    try {
      const data = await apiGet<CharacterOut>("/character");
      setCharacter(data);
      setCharacterError(null);
    } catch (e) {
      setCharacterError(e instanceof ApiError ? e.message : "Failed to load character.");
    }
  }, []);

  useEffect(() => {
    refetchCharacter();
  }, [refetchCharacter]);

  return (
    <AppDataContext.Provider value={{ character, characterError, refetchCharacter }}>
      {children}
    </AppDataContext.Provider>
  );
}

export function useAppData(): AppDataContextValue {
  const ctx = useContext(AppDataContext);
  if (ctx === null) {
    throw new Error("useAppData must be used within an AppDataProvider");
  }
  return ctx;
}
