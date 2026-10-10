// Registry of Indian coastal ports, authorities, and harbours for location resolution.
import { calculateDistanceKm } from "./distressContacts";

export interface PortLocation {
  name: string;
  lat: number;
  lon: number;
  state?: string;
  isAuthority?: boolean;
}

export const KNOWN_PORTS: PortLocation[] = [
  // 12 Primary Coastal Authorities
  { name: "Mumbai Port", lat: 18.9446, lon: 72.8347, state: "Maharashtra", isAuthority: true },
  { name: "Thoothukudi Port", lat: 8.7642, lon: 78.1348, state: "Tamil Nadu", isAuthority: true },
  { name: "Chennai Port", lat: 13.0827, lon: 80.2707, state: "Tamil Nadu", isAuthority: true },
  { name: "Kochi Port", lat: 9.9312, lon: 76.2673, state: "Kerala", isAuthority: true },
  { name: "Visakhapatnam Port", lat: 17.6868, lon: 83.2185, state: "Andhra Pradesh", isAuthority: true },
  { name: "Mangalore Port", lat: 12.8700, lon: 74.8800, state: "Karnataka", isAuthority: true },
  { name: "Rameswaram Port", lat: 9.2876, lon: 79.3129, state: "Tamil Nadu", isAuthority: true },
  { name: "Kanyakumari Port", lat: 8.0883, lon: 77.5385, state: "Tamil Nadu", isAuthority: true },
  { name: "Paradip Port", lat: 20.3164, lon: 86.6114, state: "Odisha", isAuthority: true },
  { name: "Veraval Port", lat: 20.9074, lon: 70.3678, state: "Gujarat", isAuthority: true },
  { name: "Kakinada Port", lat: 16.9891, lon: 82.2475, state: "Andhra Pradesh", isAuthority: true },
  { name: "Kolkata Port", lat: 22.5726, lon: 88.3639, state: "West Bengal", isAuthority: true },

  // Major and Intermediate Ports
  { name: "JNPT Port", lat: 18.9500, lon: 72.9500, state: "Maharashtra" },
  { name: "Kandla Port", lat: 22.9800, lon: 70.2200, state: "Gujarat" },
  { name: "Mundra Port", lat: 22.8400, lon: 69.7000, state: "Gujarat" },
  { name: "Mormugao Port", lat: 15.4100, lon: 73.8000, state: "Goa" },
  { name: "New Mangalore Port", lat: 12.9200, lon: 74.8200, state: "Karnataka" },
  { name: "Haldia Port", lat: 22.0500, lon: 88.0700, state: "West Bengal" },
  { name: "Port Blair", lat: 11.6700, lon: 92.7300, state: "Andaman & Nicobar" },
  { name: "Kavaratti Port", lat: 10.5700, lon: 72.6400, state: "Lakshadweep" },
  { name: "Porbandar Port", lat: 21.6420, lon: 69.6090, state: "Gujarat" },
  { name: "Okha Port", lat: 22.4670, lon: 69.0710, state: "Gujarat" },
  { name: "Bhavnagar Port", lat: 21.7640, lon: 72.1520, state: "Gujarat" },
  { name: "Dahej Port", lat: 21.7000, lon: 72.5830, state: "Gujarat" },
  { name: "Hazira Port", lat: 21.1100, lon: 72.6500, state: "Gujarat" },
  { name: "Daman Port", lat: 20.3970, lon: 72.8320, state: "Daman & Diu" },
  { name: "Alibaug Harbour", lat: 18.6410, lon: 72.8720, state: "Maharashtra" },
  { name: "Ratnagiri Port", lat: 16.9900, lon: 73.2900, state: "Maharashtra" },
  { name: "Malvan Port", lat: 16.0560, lon: 73.4670, state: "Maharashtra" },
  { name: "Karwar Port", lat: 14.8000, lon: 74.1200, state: "Karnataka" },
  { name: "Malpe Harbour", lat: 13.3510, lon: 74.7040, state: "Karnataka" },
  { name: "Kasaragod Port", lat: 12.4990, lon: 74.9860, state: "Kerala" },
  { name: "Kannur Port", lat: 11.8740, lon: 75.3700, state: "Kerala" },
  { name: "Beypore Port", lat: 11.1600, lon: 75.8000, state: "Kerala" },
  { name: "Ponnani Harbour", lat: 10.7760, lon: 75.9260, state: "Kerala" },
  { name: "Munambam Harbour", lat: 10.1810, lon: 76.1750, state: "Kerala" },
  { name: "Alappuzha Port", lat: 9.4980, lon: 76.3260, state: "Kerala" },
  { name: "Kollam Port", lat: 8.8800, lon: 76.5900, state: "Kerala" },
  { name: "Vizhinjam Port", lat: 8.3800, lon: 76.9900, state: "Kerala" },
  { name: "Colachel Harbour", lat: 8.1750, lon: 77.2560, state: "Tamil Nadu" },
  { name: "Mandapam Harbour", lat: 9.2780, lon: 79.1230, state: "Tamil Nadu" },
  { name: "Nagapattinam Port", lat: 10.7600, lon: 79.8400, state: "Tamil Nadu" },
  { name: "Karaikal Port", lat: 10.9250, lon: 79.8380, state: "Puducherry" },
  { name: "Cuddalore Port", lat: 11.7500, lon: 79.7700, state: "Tamil Nadu" },
  { name: "Puducherry Port", lat: 11.9330, lon: 79.8300, state: "Puducherry" },
  { name: "Ennore Port", lat: 13.2610, lon: 80.3310, state: "Tamil Nadu" },
  { name: "Krishnapatnam Port", lat: 14.2500, lon: 80.1200, state: "Andhra Pradesh" },
  { name: "Machilipatnam Port", lat: 16.1800, lon: 81.1400, state: "Andhra Pradesh" },
  { name: "Gopalpur Port", lat: 19.2600, lon: 84.9100, state: "Odisha" },
  { name: "Dhamra Port", lat: 20.8000, lon: 86.9700, state: "Odisha" },
];

/**
 * Ensures clean display format for port names (avoids double "Port Port").
 */
export function formatPortName(raw: string): string {
  const trimmed = raw.trim();
  if (/port|harbour|harbor|dock|jetty|terminal/i.test(trimmed)) {
    return trimmed;
  }
  return `${trimmed} Port`;
}

/**
 * Formats decimal latitude and longitude into maritime degree coords.
 */
export function formatCoords(lat: number, lon: number): string {
  const latStr = lat >= 0 ? `${lat.toFixed(3)}°N` : `${Math.abs(lat).toFixed(3)}°S`;
  const lonStr = lon >= 0 ? `${lon.toFixed(3)}°E` : `${Math.abs(lon).toFixed(3)}°W`;
  return `${latStr}, ${lonStr}`;
}

/**
 * Resolves a watch's coordinates to its nearest port name and formatted coordinates.
 */
export function resolveWatchLocation(
  lat: number | null | undefined,
  lon: number | null | undefined,
  homePort?: { lat: number; lon: number } | null,
  homePortName?: string | null
): { portName: string; coords: string } {
  if (lat == null || lon == null) {
    return {
      portName: "Custom Sector",
      coords: "Area boundary",
    };
  }

  const coords = formatCoords(lat, lon);

  // If user has a registered home port matching this watch within 10 km
  if (homePort && homePortName) {
    const distHome = calculateDistanceKm(lat, lon, homePort.lat, homePort.lon);
    if (distHome <= 10) {
      return {
        portName: formatPortName(homePortName),
        coords,
      };
    }
  }

  // Find the nearest known port along Indian coastlines
  let nearest = KNOWN_PORTS[0];
  let minDistance = Infinity;

  for (const p of KNOWN_PORTS) {
    const dist = calculateDistanceKm(lat, lon, p.lat, p.lon);
    if (dist < minDistance) {
      minDistance = dist;
      nearest = p;
    }
  }

  return {
    portName: formatPortName(nearest.name),
    coords,
  };
}
