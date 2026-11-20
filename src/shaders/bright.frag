#version 330 core
// Bloom bright pass + first downsample (full -> half res) with Karis average.
// Textures : uSrc (sampler2D, HDR scene colour or emission, full res)
// Uniforms : uOutSize (vec2, size of target in px), uThreshold (float), uKnee (float),
//            uKaris (float 0/1, weight taps by 1/(1+luma) to kill fireflies)
// UV is derived from gl_FragCoord, no vertex varying required.
uniform sampler2D uSrc;
uniform vec2 uOutSize;
uniform float uThreshold;
uniform float uKnee;
uniform float uKaris;
out vec4 fragColor;

float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

vec3 softKnee(vec3 c) {
    float l = luma(c);
    float K = uKnee;
    float w = clamp(l - uThreshold + K, 0.0, 2.0 * K);
    w = w * w / (4.0 * K + 1e-4);
    return c * max(l - uThreshold, w) / max(l, 1e-4);
}

vec3 fetch(vec2 uv) {
    return softKnee(max(texture(uSrc, uv).rgb, vec3(0.0)));
}

void main() {
    vec2 uv = gl_FragCoord.xy / uOutSize;
    vec2 t = 1.0 / vec2(textureSize(uSrc, 0));
    vec3 a = fetch(uv + t * vec2(-1.0, -1.0));
    vec3 b = fetch(uv + t * vec2( 1.0, -1.0));
    vec3 c = fetch(uv + t * vec2(-1.0,  1.0));
    vec3 d = fetch(uv + t * vec2( 1.0,  1.0));
    vec3 e = fetch(uv);
    vec3 col;
    if (uKaris > 0.5) {
        // 5 groups as in Jimenez (CoD AW); this variant: 4 corner taps + centre
        float wa = 1.0 / (1.0 + luma(a));
        float wb = 1.0 / (1.0 + luma(b));
        float wc = 1.0 / (1.0 + luma(c));
        float wd = 1.0 / (1.0 + luma(d));
        float we = 1.0 / (1.0 + luma(e));
        col = (a * wa + b * wb + c * wc + d * wd + e * we * 4.0) / (wa + wb + wc + wd + 4.0 * we);
    } else {
        col = (a + b + c + d) * 0.125 + e * 0.5;
    }
    fragColor = vec4(col, 1.0);
}
