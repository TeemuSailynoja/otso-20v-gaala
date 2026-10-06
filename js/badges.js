// Highlight badges and the season stories they quote.

// ==================== TIMELINE YEAR STREAM ====================
// Hand-authored season notes. 20.5 seasons is small enough to write down
// rather than generate. They are prose, and prose goes stale: when the career
// numbers were corrected, six of these lines became false next to the very
// card that contradicted them. So every number and every superlative below is
// measured against site_data by tests/js/season_stories.test.mjs — write a note
// in the checked shape ("25–2", "27 matches", "35 names", "jumps 7 to", "+179")
// and it cannot quietly become a story.
export const SEASON_STORY = {
    '2006': ["Otso's first competitive year: two seasons, 21 matches, 11–10, and 21 names on the books."],
    '2007': ["23 matches off just 18 names — the thinnest roster in the record — finishing 6th in summer and 4th in winter."],
    '2008': ["The rockiest season on record: 7–15 and 62 fewer goals scored than conceded."],
    '2009': ["The first medal arrives — winter bronze — after a 5th-place summer."],
    '2010': ["A step forward: 11–5 (69%) and outscoring opponents by 45."],
    '2011': ["First year with a podium in both seasons — winter gold, summer bronze."],
    '2012': ["Undefeated. 23 matches, 23 wins, and gold in both seasons."],
    '2013': ["25–2, double gold, and the roster jumps 7 to 35 names — the biggest single-year intake in the record."],
    '2014': ["25–2 again, and the first 170+ goal difference at +179 — winter silver ends the run of double gold."],
    '2015': ["26–2, and double gold back after a winter silver — the first of three straight titles in both seasons."],
    '2016': ["25–2 with both season titles — the fifth straight season above 90%."],
    '2017': ["The busiest season so far — 29 matches — and 26 wins anyway."],
    '2018': ["Winter gold and summer silver, with a then-record +211 goal difference."],
    '2019': ["Still the busiest year: 38 matches and 7 losses, the most in a season since 2009. Winter gold; Otso Grizzly took the summer bronze."],
    '2020': ["A short season — only 13 matches — and the winter season has no recorded placement."],
    '2021': ["The roster drops 8 to 23 names — the steepest fall in the record — and the team still goes 16–2 with double gold."],
    '2022': ["25–1, 96% — and +216, the largest goal difference in the record."],
    '2023': ["Winter gold, but a 4th-place summer — the first summer outside the podium since 2010."],
    '2024': ["23–2 and the quiet return of double gold."],
    '2025': ["Eight losses — more than in any season between 2019 and 2024 — rescued by winter gold and summer bronze."],
    '2026': ["10–0 so far and summer gold; the winter season is still to come."]
};


// Superlatives are computed, never typed: if the data changes, the badge moves.
//
// The data is a parameter, not an import, so the rules can be tested against a
// made-up set of seasons — including the ones the real record never produces.
export function computeHighlightBadges(years, trophies) {
    const yearList = Object.keys(years).sort((a, b) => a - b);
    const badges = {};
    const add = (y, text) => { (badges[y] = badges[y] || []).push(text); };
    let bestWr = null, worstWr = null, mostM = null, bestGd = null, biggestR = null, smallestR = null, biggestIn = null;
    let prevRoster = null;
    for (const y of yearList) {
        const d = years[y];
        const played = d.wins + d.losses;
        const wr = played > 0 ? d.wins / played : 0;
        const gd = d.goals_for - d.goals_against;
        if (played >= 15) {
            if (!bestWr || wr > bestWr.v) bestWr = { y, v: wr };
            if (!worstWr || wr < worstWr.v) worstWr = { y, v: wr };
            if (!smallestR || d.roster_players < smallestR.v) smallestR = { y, v: d.roster_players };
        }
        if (!mostM || d.matches > mostM.v) mostM = { y, v: d.matches };
        if (!bestGd || gd > bestGd.v) bestGd = { y, v: gd };
        if (!biggestR || d.roster_players > biggestR.v) biggestR = { y, v: d.roster_players };
        if (prevRoster !== null) {
            const delta = d.roster_players - prevRoster;
            if (!biggestIn || delta > biggestIn.v) biggestIn = { y, v: delta };
        }
        prevRoster = d.roster_players;
    }
    if (bestWr) add(bestWr.y, 'Best win rate');
    if (worstWr) add(worstWr.y, 'Toughest season');
    if (mostM) add(mostM.y, 'Most matches');
    if (bestGd) add(bestGd.y, 'Best goal difference');
    if (biggestR) add(biggestR.y, 'Largest roster');
    if (smallestR) add(smallestR.y, 'Skeleton crew');
    if (biggestIn && biggestIn.v > 0) add(biggestIn.y, `+${biggestIn.v} players`);

    const seasons = (trophies && trophies.seasons) || [];
    for (const y of yearList) {
        const rows = seasons.filter(s => String(s.year) === y);
        if (rows.filter(s => s.medal === 'gold').length === 2) add(y, 'Kulta molemmissa');
    }
    const firstMedal = seasons.filter(s => s.medal).sort((a, b) => a.year - b.year)[0];
    if (firstMedal) add(String(firstMedal.year), 'First medal');
    const undefeated = yearList.filter(y => {
        const d = years[y];
        return d.losses === 0 && d.wins >= 15;
    });
    undefeated.forEach(y => add(y, 'Undefeated'));
    return badges;
}

