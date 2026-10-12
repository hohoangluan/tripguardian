/**
 * figma-to-states.js
 *
 * Workflow notes for fetching N Figma frames via MCP and producing the
 * `states` object the MorphAnimator component expects.
 *
 * This is documentation, not a runtime module — the coding agent should follow this
 * pattern when the user references Figma frames.
 *
 * --- WORKFLOW ---
 *
 * 1. The user provides:
 *    - A Figma file URL (or it's already in conversation context)
 *    - Frame names or node ids for each state, in order
 *      (e.g., "neutral", "happy", "sleepy", "melted")
 *
 * 2. For each frame, call the Figma MCP tool to get the SVG:
 *
 *    Figma:get_design_context with the node id
 *    OR
 *    Figma:get_screenshot if you only need raster verification
 *
 *    The SVG export contains <path id="..." d="..." /> elements. The ids
 *    must already match across frames. If they don't, either:
 *    a) Ask the user to rename layers in Figma so layers with the same
 *       semantic role share names across frames (Figma converts layer
 *       names to ids on SVG export), OR
 *    b) Match them visually yourself based on position/role and rewrite
 *       the ids in the parsed SVGs before passing to the morph component.
 *
 * 3. Parse each SVG into the states-object shape:
 *
 *    {
 *      neutral: {
 *        paths: { "shape-1": "M...", "shape-2": "M..." },
 *        idle: { preset: "sway", custom: "" }
 *      },
 *      ...
 *    }
 *
 * 4. Validate: every state object should have the same set of keys in
 *    .paths. If not, log which ids are missing from which states and
 *    ask the user how to handle (fade-in/out for orphans, or fix the
 *    Figma source).
 *
 * 5. Pass to the generated MorphAnimator component as the `states` prop.
 *
 * --- ID MATCHING TIPS ---
 *
 * Figma converts layer names to ids on SVG export. Best practice:
 *   - Name semantic parts identically across frames: "left-eye",
 *     "mouth", "scarf", etc.
 *   - Avoid Figma defaults like "Vector" or "Rectangle 12" — these
 *     produce duplicate or unstable ids.
 *   - If the user can't rename in Figma (locked file, time pressure),
 *     do the matching in code by parsing and mapping.
 *
 * --- OUTPUT VERIFICATION ---
 *
 * Before passing states to the morph component, render each state's
 * paths once as a static SVG and visually confirm with the user that
 * the parse/match is correct. A wrong id mapping produces a morph that
 * looks like cosmic horror — better to catch it before animating.
 */
