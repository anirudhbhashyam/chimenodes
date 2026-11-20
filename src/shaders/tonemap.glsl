#version 330 core
// chimenodes exposure + tone map pass (complete fragment shader; kept with a
// .glsl extension per ownership list, loaded by look.py as program "tonemap").
//
// Textures: uColor  sampler2D, scene colour (display-referred sRGB as ChimeraX
//                   renders, possibly >1 after bloom).
// Uniforms: float uExposure  EV stops (params.exposure)
//           int   uMode      0 none, 1 aces (Narkowicz), 2 filmic (Hable), 3 agx
// Varying : vUV from fullscreen.vert. Output fragColor (alpha preserved).
// mode 0 with exposure 0 returns the input unchanged (exact identity).
// Pipeline: sRGB -> linear -> *2^EV -> curve -> sRGB (AgX outputs display
// referred values itself, so no extra encode).
uniform sampler2D uColor;
uniform float uExposure;
uniform int   uMode;

in vec2 vUV;
out vec4 fragColor;

vec3 toLinear(vec3 c)
{
    c = max(c, vec3(0.0));
    return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));
}
vec3 toSRGB(vec3 c)
{
    c = max(c, vec3(0.0));
    return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), c));
}

vec3 acesNarkowicz(vec3 x)
{
    return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0);
}

vec3 hable(vec3 x)
{
    const float A = 0.15, B = 0.50, C = 0.10, D = 0.20, E = 0.02, F = 0.30;
    return ((x * (A * x + C * B) + D * E) / (x * (A * x + B) + D * F)) - E / F;
}
vec3 filmic(vec3 x)
{
    const float bias = 2.0;
    const float W = 11.2;
    return clamp(hable(x * bias) / hable(vec3(W)), 0.0, 1.0);
}

// AgX (Troy Sobotka; polynomial approximation by bwrensch/iolite, as used by
// Blender "AgX" base contrast). GLSL mat3 is column-major; the rows below
// (written transposed) each sum to 1 for the inset matrix.
const mat3 AGX_INSET = mat3(
    0.842479062253094,  0.0784335999999992, 0.0792237451477643,
    0.0423282422610123, 0.878468636469772,  0.0791661274605434,
    0.0423756549057051, 0.0784336,          0.879142973793104);
const mat3 AGX_OUTSET = mat3(
     1.19687900512017,   -0.0980208811401368, -0.0990297440797205,
    -0.0528968517574562,  1.15190312990417,   -0.0989611768448433,
    -0.0529716355144438, -0.0980434501171241,  1.15107367264116);
const float AGX_MIN_EV = -12.47393;
const float AGX_MAX_EV = 4.026069;

vec3 agxContrast(vec3 x)
{
    vec3 x2 = x * x;
    vec3 x4 = x2 * x2;
    return  15.5 * x4 * x2 - 40.14 * x4 * x + 31.96 * x4
          - 6.868 * x2 * x + 0.4298 * x2 + 0.1191 * x - 0.00232;
}

vec3 agx(vec3 v)
{
    v = AGX_INSET * v;
    v = clamp(log2(max(v, vec3(1e-10))), AGX_MIN_EV, AGX_MAX_EV);
    v = (v - AGX_MIN_EV) / (AGX_MAX_EV - AGX_MIN_EV);
    v = clamp(agxContrast(clamp(v, 0.0, 1.0)), 0.0, 1.0);
    v = AGX_OUTSET * v;
    return clamp(v, 0.0, 1.0);   // display-referred (approx. gamma 2.2)
}

void main()
{
    vec4 col = texture(uColor, vUV);
    if (uMode == 0 && uExposure == 0.0) { fragColor = col; return; }
    vec3 lin = toLinear(col.rgb) * exp2(uExposure);
    vec3 outc;
    if (uMode == 1)      outc = toSRGB(acesNarkowicz(lin));
    else if (uMode == 2) outc = toSRGB(filmic(lin));
    else if (uMode == 3) outc = agx(lin);
    else                 outc = toSRGB(lin);
    fragColor = vec4(outc, col.a);
}
