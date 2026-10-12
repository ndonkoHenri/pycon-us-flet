// Runs Ionic's own ConferenceData.processData on one recorded feed and prints the
// facts our test compares, as one JSON object keyed by fixture name (#66, D-77).
//
//   node bundle.js <feed.json> <IANA zone> <UTC offset in hours>
//
// The facts are read from Ionic's output as it is, never corrected: names, tracks,
// locations and times as Ionic shows them; ids as strings.

import { readFileSync } from 'node:fs';

import { ConferenceData } from './src/app/providers/conference-data';
import { environment } from './src/environments/environment';

const [feedPath, timezone, utcOffset] = process.argv.slice(2);
environment.timezone = timezone;
environment.utcOffset = Number(utcOffset);

const storage = { create() {}, set() {} };
const ionic = new ConferenceData(null as any, null as any, storage as any, null as any);
const data = ionic.processData(JSON.parse(readFileSync(feedPath, 'utf8')));

// Newer ICU writes a narrow no-break space before "am"/"pm"; older devices wrote a space.
const label = (time: string) => time.replace(/ /g, ' ');
const id = (session: any) => String(session.id);
const ids = (sessions: any[] | undefined) => (sessions || []).map(id);

// getDays() and getTimeline() sort the days by date; so do we.
const days = [...data.schedule].sort((a: any, b: any) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
const inTimeline = new Set(days.flatMap((day: any) => day.groups.flatMap((group: any) => group.sessions)));

const sessions = data.sessions.map((s: any) => ({
  id: id(s),
  name: s.name,
  track: s.track,
  location: s.location ?? null,
  displayLocation: s.displayLocation,
  start: s.startUtc ?? null,
  end: s.endUtc ?? null,
  timeStart: label(s.timeStart),
  speakers: ids(s.speakers),
  speakerNames: s.speakerNames ?? [],
  preRegistered: Boolean(s.preRegistered),
  spanish: Boolean(s.isSpanish),
  inTimeline: inTimeline.has(s),
}));

// Collapsed rows are the only sessions whose id Ionic builds as a string,
// `${kind}-${room}-${start}`, apart from the poster details.
const collapsed = data.sessions
  .filter((s: any) => typeof s.id === 'string' && !s.id.startsWith('poster-detail-'))
  .map((s: any) => ({
    id: s.id,
    name: s.name,
    location: s.location ?? null,
    displayLocation: s.displayLocation,
    start: s.startUtc,
    end: s.endUtc,
  }));

const tally = (values: string[]) => {
  const counts: Record<string, number> = {};
  for (const value of [...values].sort()) counts[value] = (counts[value] || 0) + 1;
  return counts;
};
const seen = tally(sessions.map((s: any) => s.id));

const summary = {
  sessions: sessions.length,
  sessionsByTrack: tally(sessions.map((s: any) => s.track)),
  duplicateSessionIds: Object.keys(seen).filter((key) => seen[key] > 1),
  speakers: data.speakers.length,
  rooms: data.rooms.length,
  days: days.map((day: any) => ({
    date: day.date,
    groups: day.groups.length,
    sessions: day.groups.reduce((n: number, group: any) => n + group.sessions.length, 0),
  })),
  groupsWithoutStart: days.flatMap((day: any) =>
    day.groups.filter((group: any) => !group.startTime).map((group: any) => `${day.date} ${label(group.time)}`),
  ),
};

const timeline = Object.fromEntries(
  days.map((day: any) => [
    day.date,
    Object.fromEntries(day.groups.map((group: any) => [label(group.time), ids(group.sessions)])),
  ]),
);

const rooms = data.rooms.map((room: any) => ({ slug: room.slug, name: room.name, sessions: ids(room.sessions) }));

const speakers = data.speakers.map((speaker: any) => ({
  id: String(speaker.id),
  name: speaker.name,
  sessions: ids(speaker.sessions),
  tracks: speaker.tracks,
}));

process.stdout.write(JSON.stringify({ summary, timeline, sessions, collapsed, rooms, speakers }));
