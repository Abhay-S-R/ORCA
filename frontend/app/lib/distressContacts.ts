// Distress contacts registry and distance-based routing.
// Rule:
// - If the user is within 30 km of their registered home port:
//   Connect to the local port control / coastal marine police emergency number.
// - If the user is > 30 km away from their home port (or has no home port set):
//   Connect to the National Indian Coast Guard MRCC helpline (1554).

export type EmergencyContact = {
  name: string;
  phone: string;
  altPhone?: string;
  vhf_channel: string;
  stationName: string;
  isNational: boolean;
};

export const NATIONWIDE_MRCC: EmergencyContact = {
  name: "Indian Coast Guard MRCC",
  phone: "1554",
  altPhone: "112",
  vhf_channel: "16",
  stationName: "National Maritime Search & Rescue (Toll Free)",
  isNational: true,
};

// Authoritative 24/7 port signal stations, coastal police, and MRSC units
export const PORT_EMERGENCY_CONTACTS: Record<string, EmergencyContact> = {
  "thoothukudi": {
    name: "Thoothukudi Port Control & Marine Police",
    phone: "0461-2352290",
    altPhone: "1093",
    vhf_channel: "16",
    stationName: "Thoothukudi Coastal Security Group",
    isNational: false,
  },
  "chennai": {
    name: "Chennai Port Signal Station",
    phone: "044-25362201",
    altPhone: "044-25395018",
    vhf_channel: "16",
    stationName: "Chennai Port Trust & Coastal Police",
    isNational: false,
  },
  "kochi": {
    name: "Cochin Port Control & Marine Police",
    phone: "0484-2582400",
    altPhone: "1093",
    vhf_channel: "16",
    stationName: "Cochin Port Signal Station & Coastal Police Kerala",
    isNational: false,
  },
  "kochi / cochin": {
    name: "Cochin Port Control & Marine Police",
    phone: "0484-2582400",
    altPhone: "1093",
    vhf_channel: "16",
    stationName: "Cochin Port Signal Station & Coastal Police Kerala",
    isNational: false,
  },
  "cochin": {
    name: "Cochin Port Control & Marine Police",
    phone: "0484-2582400",
    altPhone: "1093",
    vhf_channel: "16",
    stationName: "Cochin Port Signal Station & Coastal Police Kerala",
    isNational: false,
  },
  "visakhapatnam": {
    name: "Visakhapatnam Port Signal Station",
    phone: "0891-2873333",
    altPhone: "1093",
    vhf_channel: "16",
    stationName: "Vizag Port Control & Marine Police",
    isNational: false,
  },
  "mangalore": {
    name: "New Mangalore Port Control Station",
    phone: "0824-2407298",
    altPhone: "1093",
    vhf_channel: "16",
    stationName: "New Mangalore Port Signal Station & CSG",
    isNational: false,
  },
  "mumbai": {
    name: "Mumbai Port Control & Marine Police",
    phone: "022-22612348",
    altPhone: "022-24388065",
    vhf_channel: "16",
    stationName: "Mumbai Port Trust & Yellow Gate Coastal Police",
    isNational: false,
  },
  "rameswaram": {
    name: "Rameswaram Coastal Security Police",
    phone: "04573-221213",
    altPhone: "1093",
    vhf_channel: "16",
    stationName: "Pamban & Rameswaram Marine Police Station",
    isNational: false,
  },
  "kanyakumari": {
    name: "Kanyakumari Marine Police Station",
    phone: "04652-246260",
    altPhone: "1093",
    vhf_channel: "16",
    stationName: "Kanyakumari Coastal Security Group",
    isNational: false,
  },
  "paradip": {
    name: "Paradip Port Signal Station",
    phone: "06722-222157",
    altPhone: "1093",
    vhf_channel: "16",
    stationName: "Paradip Port Control & Marine Police",
    isNational: false,
  },
  "veraval": {
    name: "Veraval Port Control Station",
    phone: "02876-220002",
    altPhone: "1093",
    vhf_channel: "16",
    stationName: "Veraval Port Control & Gujarat Marine Police",
    isNational: false,
  },
  "kakinada": {
    name: "Kakinada Port Signal Station",
    phone: "0884-2364016",
    altPhone: "1093",
    vhf_channel: "16",
    stationName: "Kakinada Port Control & Marine Police",
    isNational: false,
  },
  "kolkata": {
    name: "Haldia Port Signal Station",
    phone: "03224-252100",
    altPhone: "1093",
    vhf_channel: "16",
    stationName: "Haldia Port Control & Marine Police",
    isNational: false,
  },
  "kolkata / haldia": {
    name: "Haldia Port Signal Station",
    phone: "03224-252100",
    altPhone: "1093",
    vhf_channel: "16",
    stationName: "Haldia Port Control & Marine Police",
    isNational: false,
  },
};

const EARTH_RADIUS_KM = 6371;

/**
 * Calculates Great-Circle distance between two coordinates in kilometres.
 */
export function calculateDistanceKm(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number {
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return EARTH_RADIUS_KM * c;
}

export const HOME_PORT_MAX_RADIUS_KM = 80;

export type DistressResolution = {
  primary: EmergencyContact;
  nationwide: EmergencyContact;
  isWithinHomePortRadius: boolean;
  distanceKm: number | null;
  homePortName: string | null;
  radiusLimitKm: number;
  statusMessage: string;
};

/**
 * Resolves whether the current distress call routes to the local home port
 * emergency number (<= 30 km) or escalates to the nationwide MRCC 1554 (> 30 km).
 */
export function resolveDistressContact(
  currentPos: { lat: number; lon: number } | null | undefined,
  homePort: { lat: number; lon: number } | null | undefined,
  homePortName?: string | null
): DistressResolution {
  // If no home port registered: direct to national helpline
  if (!homePort) {
    return {
      primary: NATIONWIDE_MRCC,
      nationwide: NATIONWIDE_MRCC,
      isWithinHomePortRadius: false,
      distanceKm: null,
      homePortName: null,
      radiusLimitKm: HOME_PORT_MAX_RADIUS_KM,
      statusMessage: "No registered home port — routed to National Coast Guard MRCC.",
    };
  }

  // Position reference: use current position if available, else home port
  const pos = currentPos ?? homePort;
  const distance = calculateDistanceKm(pos.lat, pos.lon, homePort.lat, homePort.lon);
  const portKey = (homePortName ?? "").toLowerCase().trim();
  const localContact =
    PORT_EMERGENCY_CONTACTS[portKey] ||
    Object.entries(PORT_EMERGENCY_CONTACTS).find(([k]) => portKey.includes(k))?.[1];

  if (distance <= HOME_PORT_MAX_RADIUS_KM && localContact) {
    return {
      primary: localContact,
      nationwide: NATIONWIDE_MRCC,
      isWithinHomePortRadius: true,
      distanceKm: distance,
      homePortName: homePortName ?? "Home Port",
      radiusLimitKm: HOME_PORT_MAX_RADIUS_KM,
      statusMessage: `Within ${distance.toFixed(1)} km of ${homePortName ?? "home port"} (≤ 30 km radius). Routed to Local Port Emergency Unit.`,
    };
  }

  // Beyond 30 km radius or no specific local port number found
  return {
    primary: NATIONWIDE_MRCC,
    nationwide: NATIONWIDE_MRCC,
    isWithinHomePortRadius: false,
    distanceKm: distance,
    homePortName: homePortName ?? null,
    radiusLimitKm: HOME_PORT_MAX_RADIUS_KM,
    statusMessage: `${distance.toFixed(1)} km from ${homePortName ?? "home port"} (> 30 km radius). Switched to National Coast Guard Helpline.`,
  };
}
