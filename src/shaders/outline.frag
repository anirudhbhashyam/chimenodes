#version 330 core
// Depth-based outline: Sobel on depth relative to z, plus Laplacian crease term (normal change).
// Textures : uColor (sampler2D HDR colour), uDepth (sampler2D)
// Uniforms : uNear, uFar (float), uOrtho (int), uStrength (float 0..1 = params.outline),
//            uThickness (float px, ~ max(1, height/1080) * (1 + strength)),
//            uColorOut (vec3 line colour, default black)
uniform sampler2D uColor;
uniform sampler2D uDepth;
uniform float uNear;
uniform float uFar;
uniform int uOrtho;
uniform float uStrength;
uniform float uThickness;
uniform vec3 uColorOut;
out vec4 fragColor;

float lin(vec2 uv) {
    float d = min(texture(uDepth, uv).r, 0.99999);
    if (uOrtho != 0) return uNear + d * (uFar - uNear);
    return uNear * uFar / max(uFar - d * (uFar - uNear), 1e-6);
}

void main() {
    vec2 size = vec2(textureSize(uColor, 0));
    vec2 uv = gl_FragCoord.xy / size;
    vec2 t = uThickness / size;
    float zc = lin(uv);
    float zl = lin(uv + vec2(-t.x, 0.0)), zr = lin(uv + vec2(t.x, 0.0));
    float zu = lin(uv + vec2(0.0, t.y)),  zd = lin(uv + vec2(0.0, -t.y));
    float zul = lin(uv + vec2(-t.x, t.y)), zur = lin(uv + vec2(t.x, t.y));
    float zdl = lin(uv + vec2(-t.x, -t.y)), zdr = lin(uv + vec2(t.x, -t.y));
    float gx = (zur + 2.0 * zr + zdr) - (zul + 2.0 * zl + zdl);
    float gy = (zul + 2.0 * zu + zur) - (zdl + 2.0 * zd + zdr);
    float sob = length(vec2(gx, gy)) / (4.0 * zc);          // relative depth change
    // normal-from-depth proxy: second derivative flags creases that Sobel misses
    float lap = abs(zl + zr - 2.0 * zc) + abs(zu + zd - 2.0 * zc);
    lap = lap / zc;
    float e = max(smoothstep(0.004, 0.02, sob), smoothstep(0.01, 0.05, lap) * 0.6);
    vec4 col = texture(uColor, uv);
    col.rgb = mix(col.rgb, uColorOut, clamp(e * uStrength, 0.0, 1.0));
    fragColor = col;
}
