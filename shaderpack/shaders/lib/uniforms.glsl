uniform sampler2D gtexture;
uniform sampler2D lightmap;
uniform sampler2D normals;
uniform sampler2D specular;
uniform sampler2D noisetex;

uniform sampler2D colortex0;
uniform sampler2D colortex1;
uniform sampler2D colortex2;
uniform sampler2D colortex3;
uniform sampler2D colortex6;
uniform sampler2D depthtex0;
uniform sampler2D depthtex1;

uniform sampler2DShadow shadowtex0;
uniform sampler2DShadow shadowtex1;
uniform sampler2D shadowcolor0;

uniform mat4 gbufferModelView;
uniform mat4 gbufferModelViewInverse;
uniform mat4 gbufferProjection;
uniform mat4 gbufferProjectionInverse;
uniform mat4 shadowModelView;
uniform mat4 shadowModelViewInverse;
uniform mat4 shadowProjection;

uniform vec3 sunPosition;
uniform vec3 moonPosition;
uniform vec3 shadowLightPosition;
uniform vec3 upPosition;
uniform vec3 cameraPosition;
uniform vec3 fogColor;
uniform vec3 skyColor;
uniform vec4 entityColor;

uniform float frameTimeCounter;
uniform float rainStrength;
uniform float wetness;
uniform float viewWidth;
uniform float viewHeight;
uniform float near;
uniform float far;
uniform float nightVision;
uniform float blindness;
uniform float darknessFactor;
uniform float alphaTestRef;

uniform int worldTime;
uniform int isEyeInWater;
uniform int heldBlockLightValue;
uniform int heldBlockLightValue2;
uniform int frameCounter;
uniform int renderStage;

uniform ivec2 eyeBrightnessSmooth;

#ifndef MC_RENDER_STAGE_SUN
    #define MC_RENDER_STAGE_SKY 1
    #define MC_RENDER_STAGE_SUNSET 2
    #define MC_RENDER_STAGE_CUSTOM_SKY 3
    #define MC_RENDER_STAGE_SUN 4
    #define MC_RENDER_STAGE_MOON 5
    #define MC_RENDER_STAGE_STARS 6
    #define MC_RENDER_STAGE_VOID 7
#endif

// material ids (block.properties) and internal ids written to colortex3.a
#define ID_WATER 10001
#define ID_LEAVES 10002
#define ID_PLANT 10003
#define ID_PLANT_UPPER 10004
#define ID_EMISSIVE 10005
#define ID_ICE 10006

#define MAT_NONE 0
#define MAT_DEFAULT 1
#define MAT_FOLIAGE 2
#define MAT_ENTITY 3
#define MAT_HAND 4
#define MAT_NOREFLECT 5
