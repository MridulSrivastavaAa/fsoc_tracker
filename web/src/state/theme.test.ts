import { describe, expect, it } from 'vitest';
import { THEMES, THEME_CONFIGS, applyTheme, STATE_HEX } from './store';

describe('Curated 4 Theme Palettes', () => {
  it('strictly defines exactly 4 themes', () => {
    expect(THEMES).toHaveLength(4);
    const ids = THEMES.map((t) => t.id);
    expect(ids).toEqual(['mission-control', 'orbital-graphite', 'aerospace-smoked-cream', 'dusky-solar-cream']);
  });

  it('matches Palette 01: Mission Control (Deep Space Navy)', () => {
    const p1 = THEME_CONFIGS['mission-control'];
    expect(p1.name).toBe('Mission Control');
    expect(p1.subtitle).toBe('Deep Space Navy');
    expect(p1.viewport).toBe('#050912');
    expect(p1.panelSurface).toBe('#0B1320');
    expect(p1.elevatedSurface).toBe('#111D30');
    expect(p1.borderDivider).toBe('#1D2F4A');
    expect(p1.primaryText).toBe('#F4F8FD');
    expect(p1.secondaryText).toBe('#A5BCD7');
    expect(p1.tertiaryText).toBe('#8AA4C2');
    expect(p1.strongText).toBe('#FFFFFF');
    expect(p1.isroOrange).toBe('#FF8C1A');
    expect(p1.orangeHighlight).toBe('#FFA347');
    expect(p1.successLock).toBe('#2DD36F');
    expect(p1.alertLost).toBe('#FF4D4D');
    expect(p1.spatialBlue).toBe('#1E90FF');
    expect(p1.axisColor).toBe('#F4F8FD');
  });

  it('matches Palette 02: Orbital Graphite (Smoked Cream)', () => {
    const p2 = THEME_CONFIGS['orbital-graphite'];
    expect(p2.name).toBe('Orbital Graphite');
    expect(p2.subtitle).toBe('Smoked Cream');
    expect(p2.viewport).toBe('#0B0D0F');
    expect(p2.spaceSecondary).toBe('#15181B');
    expect(p2.panelSurface).toBe('#202428');
    expect(p2.elevatedSurface).toBe('#2B3034');
    expect(p2.borderDivider).toBe('#41474C');
    expect(p2.primaryText).toBe('#E4D7BD');
    expect(p2.secondaryText).toBe('#C4B594');
    expect(p2.tertiaryText).toBe('#A59678');
    expect(p2.strongText).toBe('#F5EAD4');
    expect(p2.isroOrange).toBe('#E97824');
    expect(p2.orangeHighlight).toBe('#F28E42');
    expect(p2.successLock).toBe('#3BA35C');
    expect(p2.alertLost).toBe('#D9534F');
    expect(p2.spatialBlue).toBe('#3B7189');
    expect(p2.axisColor).toBe('#F5EAD4');
  });

  it('matches Palette 03: Aerospace Smoked Cream (Black-Side Cream)', () => {
    const p3 = THEME_CONFIGS['aerospace-smoked-cream'];
    expect(p3.name).toBe('Aerospace Smoked Cream');
    expect(p3.subtitle).toBe('Black-Side Cream');
    expect(p3.viewport).toBe('#0B1117');
    expect(p3.spaceSecondary).toBe('#111B23');
    expect(p3.panelSurface).toBe('#24211B');
    expect(p3.elevatedSurface).toBe('#2F2B23');
    expect(p3.borderDivider).toBe('#4A4234');
    expect(p3.primaryText).toBe('#E6D8BE');
    expect(p3.secondaryText).toBe('#C5B697');
    expect(p3.tertiaryText).toBe('#A6977A');
    expect(p3.strongText).toBe('#F6ECD6');
    expect(p3.isroOrange).toBe('#E87522');
    expect(p3.orangeHighlight).toBe('#F28C38');
    expect(p3.successLock).toBe('#299653');
    expect(p3.alertLost).toBe('#D84D45');
    expect(p3.spatialBlue).toBe('#3B7189');
    expect(p3.axisColor).toBe('#F6ECD6');
  });

  it('matches Palette 04: Dusky Solar Cream (Weathered Khaki-Cream)', () => {
    const p4 = THEME_CONFIGS['dusky-solar-cream'];
    expect(p4.name).toBe('Dusky Solar Cream');
    expect(p4.subtitle).toBe('Weathered Khaki-Cream');
    expect(p4.viewport).toBe('#0B1117');
    expect(p4.spaceSecondary).toBe('#111B23');
    expect(p4.panelSurface).toBe('#D0C39E');
    expect(p4.elevatedSurface).toBe('#A89872');
    expect(p4.borderDivider).toBe('#6E6041');
    expect(p4.primaryText).toBe('#100E0A');
    expect(p4.secondaryText).toBe('#262014');
    expect(p4.tertiaryText).toBe('#3D3422');
    expect(p4.strongText).toBe('#050403');
    expect(p4.isroOrange).toBe('#E87522');
    expect(p4.orangeHighlight).toBe('#F28C38');
    expect(p4.successLock).toBe('#299653');
    expect(p4.alertLost).toBe('#D84D45');
    expect(p4.spatialBlue).toBe('#3B7189');
    expect(p4.axisColor).toBe('#050403');
  });

  it('updates document dataset and STATE_HEX upon applyTheme', () => {
    const doc = { documentElement: { dataset: {} as Record<string, string> } };
    (globalThis as unknown as { document: unknown }).document = doc;

    applyTheme('orbital-graphite');
    expect(doc.documentElement.dataset.theme).toBe('orbital-graphite');
    expect(STATE_HEX.LOCKED).toBe('#3BA35C');
    expect(STATE_HEX.SEARCHING).toBe('#E97824');
    expect(STATE_HEX.LOST).toBe('#D9534F');

    applyTheme('mission-control');
    expect(doc.documentElement.dataset.theme).toBe('mission-control');
    expect(STATE_HEX.LOCKED).toBe('#2DD36F');
    expect(STATE_HEX.SEARCHING).toBe('#FF8C1A');
    expect(STATE_HEX.LOST).toBe('#FF4D4D');
  });
});
