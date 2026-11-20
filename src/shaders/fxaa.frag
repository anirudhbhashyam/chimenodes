#version 330 core
// FXAA 3.11 (quality, condensed) on LDR colour. Luma computed from RGB.
// Textures : uColor (sampler2D LDR, bilinear filtered)
// Uniforms : uSubpix (float 0.75 default), uEdgeThreshold (0.166), uEdgeThresholdMin (0.0833)
uniform sampler2D uColor;
uniform float uSubpix;
uniform float uEdgeThreshold;
uniform float uEdgeThresholdMin;
out vec4 fragColor;

float lum(vec3 c) { return dot(clamp(c, 0.0, 1.0), vec3(0.299, 0.587, 0.114)); }
float lumAt(vec2 uv, ivec2 o) { return lum(textureOffset(uColor, uv, o).rgb); }

const float STEPS[8] = float[8](1.0, 1.0, 1.0, 1.0, 1.0, 1.5, 2.0, 4.0);

void main() {
    vec2 size = vec2(textureSize(uColor, 0));
    vec2 rcp = 1.0 / size;
    vec2 uv = gl_FragCoord.xy * rcp;
    vec4 cM4 = texture(uColor, uv);
    float lM = lum(cM4.rgb);
    float lN = lumAt(uv, ivec2(0, 1)), lS = lumAt(uv, ivec2(0, -1));
    float lW = lumAt(uv, ivec2(-1, 0)), lE = lumAt(uv, ivec2(1, 0));
    float lMax = max(max(lN, lS), max(lW, max(lE, lM)));
    float lMin = min(min(lN, lS), min(lW, min(lE, lM)));
    float range = lMax - lMin;
    if (range < max(uEdgeThresholdMin, lMax * uEdgeThreshold)) { fragColor = cM4; return; }

    float lNW = lumAt(uv, ivec2(-1, 1)), lNE = lumAt(uv, ivec2(1, 1));
    float lSW = lumAt(uv, ivec2(-1, -1)), lSE = lumAt(uv, ivec2(1, -1));
    float lNS = lN + lS, lWE = lW + lE;
    float subpixA = (lNS + lWE) * 2.0 + (lNW + lNE) + (lSW + lSE);
    float subpixB = subpixA / 12.0 - lM;
    float subpixC = clamp(abs(subpixB) / range, 0.0, 1.0);
    float subpixD = (-2.0 * subpixC + 3.0) * subpixC * subpixC * uSubpix;

    float edgeH = abs(-2.0 * lW + (lNW + lSW)) + abs(-2.0 * lM + lNS) * 2.0 + abs(-2.0 * lE + (lNE + lSE));
    float edgeV = abs(-2.0 * lN + (lNW + lNE)) + abs(-2.0 * lM + lWE) * 2.0 + abs(-2.0 * lS + (lSW + lSE));
    bool horz = edgeH >= edgeV;

    float l1 = horz ? lS : lW;
    float l2 = horz ? lN : lE;
    float g1 = l1 - lM, g2 = l2 - lM;
    bool p1 = abs(g1) >= abs(g2);
    float grad = 0.25 * max(abs(g1), abs(g2));
    float stepLen = horz ? rcp.y : rcp.x;
    float lAvg;
    if (p1) { stepLen = -stepLen; lAvg = 0.5 * (l1 + lM); } else { lAvg = 0.5 * (l2 + lM); }

    vec2 pos = uv;
    if (horz) pos.y += stepLen * 0.5; else pos.x += stepLen * 0.5;
    vec2 off = horz ? vec2(rcp.x, 0.0) : vec2(0.0, rcp.y);
    vec2 pA = pos - off, pB = pos + off;
    float eA = lum(texture(uColor, pA).rgb) - lAvg;
    float eB = lum(texture(uColor, pB).rgb) - lAvg;
    bool doneA = abs(eA) >= grad, doneB = abs(eB) >= grad;
    for (int i = 1; i < 8 && !(doneA && doneB); ++i) {
        float s = STEPS[i];
        if (!doneA) { pA -= off * s; eA = lum(texture(uColor, pA).rgb) - lAvg; doneA = abs(eA) >= grad; }
        if (!doneB) { pB += off * s; eB = lum(texture(uColor, pB).rgb) - lAvg; doneB = abs(eB) >= grad; }
    }
    float dA = horz ? (uv.x - pA.x) : (uv.y - pA.y);
    float dB = horz ? (pB.x - uv.x) : (pB.y - uv.y);
    bool dirA = dA < dB;
    float dMin = min(dA, dB);
    float span = dA + dB;
    bool goodSpan = dirA ? ((eA < 0.0) != (lM - lAvg < 0.0)) : ((eB < 0.0) != (lM - lAvg < 0.0));
    float pixOff = goodSpan ? (0.5 - dMin / span) : 0.0;
    float finalOff = max(pixOff, subpixD);
    vec2 fuv = uv;
    if (horz) fuv.y += finalOff * stepLen; else fuv.x += finalOff * stepLen;
    fragColor = vec4(texture(uColor, fuv).rgb, cM4.a);
}
