export const person = {
  name: 'Otis',
  handle: '@otispell',
};

export const nav = [
  {label: 'Work', href: '#work'},
  {label: 'Notes', href: '#notes'},
];

export const bio = [
  'I make faces for a living.',
  'Eleven years of sculpting and animating cartoon characters — mostly for games, a few for cereal boxes, one for a very confused bank. I still can’t draw hands.',
  'These days I build small tools that let anyone rig a face in an afternoon. I write about what breaks every other Sunday:',
];

/** Invented outlets — set as wordmarks in different faces, like a press strip. */
export const press = [
  {name: 'The Polygon Review', font: 'font-serif italic'},
  {name: 'RIGGED', font: 'font-wide tracking-[0.08em]'},
  {name: 'frameline', font: 'font-display font-black lowercase tracking-[-0.04em]'},
  {name: 'Keyframe Quarterly', font: 'font-serif'},
  {name: 'TOON/DAILY', font: 'font-mono tracking-[0.04em]'},
  {name: 'Squash & Stretch', font: 'font-display font-medium italic'},
];

/**
 * Every expression is registered to the same 2:3 bust framing, padded to a
 * square, so they swap in place. A file that fails to load falls back to the base face
 * (a missing grab face falls back to g_grimace).
 */
export const faces = {
  base: {src: '/faces/base.webp', mood: 'chill'},
  l_left: {src: '/faces/l_left.webp', mood: 'watching you'},
  l_right: {src: '/faces/l_right.webp', mood: 'watching you'},
  x_cross: {src: '/faces/x_cross.webp', mood: 'suspicious'},
  x_tongue: {src: '/faces/x_tongue.webp', mood: 'goofy'},
  x_shock: {src: '/faces/x_shock.webp', mood: 'startled'},
  x_laugh: {src: '/faces/x_laugh.webp', mood: 'cackling'},
  x_skeptic: {src: '/faces/x_skeptic.webp', mood: 'unconvinced'},
  x_whistle: {src: '/faces/x_whistle.webp', mood: 'innocent'},
  x_smug: {src: '/faces/x_smug.webp', mood: 'smug'},
  x_dizzy: {src: '/faces/x_dizzy.webp', mood: 'seeing stars'},
  g_grimace: {src: '/faces/g_grimace.webp', mood: 'being squeezed'},
  g_ouch: {src: '/faces/g_ouch.webp', mood: 'OW'},
  g_squish: {src: '/faces/g_squish.webp', mood: 'pinched'},
} as const;

export type FaceKey = keyof typeof faces;

/** Faces dealt at random when a stretch is let go. */
export const releaseFaces: FaceKey[] = ['x_tongue', 'x_laugh', 'x_skeptic', 'x_whistle', 'x_smug', 'x_cross'];

/**
 * Landmarks in image UV (0–1, v from the top) measured on the prepared faces
 * (2:3 busts padded to square, so the sweater spans u 0.167–0.833 and meets
 * the frame edge from v 0.845 down). The disc is drawn in the same space and
 * sized so its arc clips the shoulders before they reach those edges.
 */
export const rig = {
  disc: {x: 0.5, y: 0.58, r: 0.41},
  nose: {x: 0.505, y: 0.505, r: 0.04},
  cheeks: [
    {x: 0.385, y: 0.53},
    {x: 0.625, y: 0.53},
  ],
  face: {x: 0.5, y: 0.51, rx: 0.175, ry: 0.23},
  hairLine: 0.26,
  /** |u − 0.5| beyond which a grab above the jaw is the ears / side hair. */
  sides: 0.19,
};
