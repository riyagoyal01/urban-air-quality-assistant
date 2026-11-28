export type RequestSequence = {
  begin: () => number;
  isCurrent: (sequence: number) => boolean;
  invalidate: () => void;
};

export function createRequestSequence(): RequestSequence {
  let current = 0;

  return {
    begin: () => {
      current += 1;
      return current;
    },
    isCurrent: (sequence: number) => sequence === current,
    invalidate: () => {
      current += 1;
    },
  };
}

export function buildIndoorAdvicePayload(
  pm2_5: number | null,
  hasPurifier: "yes" | "no",
  cookingFuel: string,
  pm2_5_unit?: string | null,
) {
  return {
    pm2_5,
    pm2_5_unit: pm2_5_unit ?? null,
    has_air_purifier: hasPurifier === "yes",
    cooking_fuel: cookingFuel,
  };
}

export function isLocationRequestCurrent(
  sequence: RequestSequence,
  requestSequence: number,
  activeLocation: { latitude: number; longitude: number } | null,
  requestedLocation: { latitude: number; longitude: number },
) {
  return sequence.isCurrent(requestSequence) &&
    activeLocation?.latitude === requestedLocation.latitude &&
    activeLocation?.longitude === requestedLocation.longitude;
}

export function buildChatPayload(
  question: string,
  data: {
    current: Record<string, number | null>;
    current_units?: Record<string, string>;
  },
  hasPurifier: "yes" | "no",
  cookingFuel: string,
  household: string,
  recommendations: unknown[],
  history: Array<{ role?: unknown; content?: unknown }> = [],
) {
  return {
    question,
    pm2_5: data.current.pm2_5 ?? null,
    pm10: data.current.pm10 ?? null,
    ozone: data.current.ozone ?? null,
    nitrogen_dioxide: data.current.nitrogen_dioxide ?? null,
    pm2_5_unit: data.current_units?.pm2_5 ?? null,
    pm10_unit: data.current_units?.pm10 ?? null,
    ozone_unit: data.current_units?.ozone ?? null,
    nitrogen_dioxide_unit: data.current_units?.nitrogen_dioxide ?? null,
    household,
    has_air_purifier: hasPurifier === "yes",
    cooking_fuel: cookingFuel,
    recommendations,
    history: history.reduce<Array<{ role: "user" | "assistant"; content: string }>>(
      (valid, item) => {
        if ((item.role === "user" || item.role === "assistant") &&
            typeof item.content === "string" &&
            item.content.trim().length > 0) {
          valid.push({
            role: item.role,
            content: item.content.trim(),
          });
        }
        return valid;
      },
      [],
    ).slice(-20),
  };
}
