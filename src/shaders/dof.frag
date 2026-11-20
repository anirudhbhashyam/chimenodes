#version 330 core
// Depth of field: CoC from linearised depth, golden-angle gather, CoC-weighted.
// Textures : uColor (sampler2D HDR colour), uDepth (sampler2D depth, 0..1 window depth)
// Uniforms : uNear, uFar (float, ctx.near/ctx.far), uFocus (float distance in scene units),
//            uAperture (float 0..1+, scales CoC growth), uMaxCoc (float, max CoC radius in px;
//            = dof * 0.03 * image_height), uTaps (int 8..32), uOrtho (int 0/1)
uniform sampler2D uColor;
uniform sampler2D uDepth;
uniform float uNear;
uniform float uFar;
uniform float uFocus;
uniform float uAperture;
uniform float uMaxCoc;
uniform int uTaps;
uniform int uOrtho;
out vec4 fragColor;

float linearize(float d) {
    if (uOrtho != 0) return uNear + d * (uFar - uNear);
    return uNear * uFar / max(uFar - d * (uFar - uNear), 1e-6);
}

// Returns signed-free CoC radius in pixels.
float cocPx(float d) {
    if (d >= 1.0) d = 0.9999;   // background: treat as far plane
    float z = linearize(d);
    float c = abs(z - uFocus) / max(uFocus, 1e-4) * uAperture;
    return min(c, 1.0) * uMaxCoc;
}

void main() {
    vec2 size = vec2(textureSize(uColor, 0));
    vec2 uv = gl_FragCoord.xy / size;
    float c0 = cocPx(texture(uDepth, uv).r);
    vec4 centre = texture(uColor, uv);
    if (uMaxCoc < 0.5) { fragColor = centre; return; }
    vec3 acc = centre.rgb;
    float wsum = 1.0;
    const float GA = 2.39996323;
    for (int i = 1; i < uTaps; ++i) {
        float r = sqrt(float(i) / float(uTaps));
        float a = float(i) * GA;
        vec2 off = vec2(cos(a), sin(a)) * r;
        float distPx = r * max(c0, 1.0);
        vec2 suv = uv + off * max(c0, 1.0) / size;
        float cs = cocPx(texture(uDepth, suv).r);
        // sample contributes if its own blur disc reaches us, or we are blurry enough ourselves
        float reach = min(cs, c0);
        float w = smoothstep(0.0, 1.0, reach - distPx + 1.0);
        // in-focus samples never bleed over a sharper centre much (avoids halos)
        w *= (cs >= c0 * 0.5) ? 1.0 : 0.25;
        acc += texture(uColor, suv).rgb * w;
        wsum += w;
    }
    fragColor = vec4(acc / wsum, centre.a);
}
