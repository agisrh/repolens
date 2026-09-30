"""Framework detection (with versions), mobile platform settings, and infrastructure/CI."""

from __future__ import annotations

import json
import re

import yaml

from repolens.i18n import t
from repolens.repo import Repo

# (display name, category, ecosystem prefix, dependency names that identify it)
FRAMEWORK_RULES = [
    (
        "Spring Boot",
        "Backend framework",
        "Java",
        [
            "org.springframework.boot:spring-boot-starter",
            "org.springframework.boot:spring-boot-starter-web",
            "org.springframework.boot:spring-boot-starter-webflux",
        ],
    ),
    ("Laravel", "Backend framework", "PHP", ["laravel/framework"]),
    ("Lumen", "Backend framework", "PHP", ["laravel/lumen-framework"]),
    (
        "CodeIgniter 4",
        "Backend framework",
        "PHP",
        ["codeigniter4/framework", "codeigniter4/codeigniter4"],
    ),
    ("Symfony", "Backend framework", "PHP", ["symfony/framework-bundle"]),
    ("Next.js", "Fullstack framework", "Node", ["next"]),
    ("Nuxt", "Fullstack framework", "Node", ["nuxt"]),
    ("Remix", "Fullstack framework", "Node", ["@remix-run/react"]),
    ("React", "Frontend library", "Node", ["react"]),
    ("React Native", "Mobile framework", "Node", ["react-native"]),
    ("Expo", "Mobile framework", "Node", ["expo"]),
    ("Vue", "Frontend framework", "Node", ["vue"]),
    ("Angular", "Frontend framework", "Node", ["@angular/core"]),
    ("Svelte", "Frontend framework", "Node", ["svelte"]),
    ("Express", "Backend framework", "Node", ["express"]),
    ("NestJS", "Backend framework", "Node", ["@nestjs/core"]),
    ("Fastify", "Backend framework", "Node", ["fastify"]),
    ("Vite", "Build tool", "Node", ["vite"]),
    ("TypeScript", "Language", "Node", ["typescript"]),
    ("Tailwind CSS", "Styling", "Node", ["tailwindcss"]),
    ("Redux", "State management", "Node", ["redux", "@reduxjs/toolkit"]),
    ("Prisma", "ORM", "Node", ["prisma", "@prisma/client"]),
    ("Drizzle ORM", "ORM", "Node", ["drizzle-orm"]),
    ("TypeORM", "ORM", "Node", ["typeorm"]),
    ("Sequelize", "ORM", "Node", ["sequelize"]),
    ("Mongoose", "ODM", "Node", ["mongoose"]),
    ("Django", "Backend framework", "Python", ["django", "Django"]),
    ("Flask", "Backend framework", "Python", ["flask", "Flask"]),
    ("FastAPI", "Backend framework", "Python", ["fastapi"]),
    ("Gin", "Backend framework", "Go", ["github.com/gin-gonic/gin"]),
    ("Echo", "Backend framework", "Go", ["github.com/labstack/echo/v4"]),
    ("Fiber", "Backend framework", "Go", ["github.com/gofiber/fiber/v2"]),
    ("Ruby on Rails", "Backend framework", "Ruby", ["rails"]),
    ("flutter_bloc", "State management", "Dart", ["flutter_bloc"]),
    ("Riverpod", "State management", "Dart", ["flutter_riverpod", "hooks_riverpod"]),
    ("Provider", "State management", "Dart", ["provider"]),
    ("GetX", "State management", "Dart", ["get"]),
    ("go_router", "Routing", "Dart", ["go_router"]),
    ("Dio", "HTTP client", "Dart", ["dio"]),
    ("Hive", "Local database", "Dart", ["hive", "hive_flutter"]),
    ("sqflite", "Local database", "Dart", ["sqflite"]),
    ("Drift", "Local database", "Dart", ["drift"]),
    ("Firebase", "Backend service", "Dart", ["firebase_core"]),
    ("Firebase", "Backend service", "Node", ["firebase", "firebase-admin"]),
    ("Spring Data JPA", "ORM", "Java", ["org.springframework.boot:spring-boot-starter-data-jpa"]),
    (
        "Spring Security",
        "Security",
        "Java",
        ["org.springframework.boot:spring-boot-starter-security"],
    ),
    ("Lombok", "Library", "Java", ["org.projectlombok:lombok"]),
    ("Laravel Sanctum", "Auth", "PHP", ["laravel/sanctum"]),
    ("Laravel Passport", "Auth", "PHP", ["laravel/passport"]),
    ("tymon/jwt-auth", "Auth", "PHP", ["tymon/jwt-auth"]),
]


def _version(dep: dict) -> str | None:
    return dep.get("resolved") or dep.get("declared")


def frameworks(repo: Repo, manifests: list[dict]) -> list[dict]:
    found: dict[str, dict] = {}

    def add(name, category, version, source):
        if name not in found or (version and not found[name]["version"]):
            found[name] = {"name": name, "category": category, "version": version, "source": source}

    for m in manifests:
        eco = m["ecosystem"]
        by_name = {d["name"]: d for d in m["dependencies"]}
        for name, category, prefix, dep_names in FRAMEWORK_RULES:
            if not eco.startswith(prefix):
                continue
            for dep_name in dep_names:
                if dep_name in by_name:
                    add(name, category, _version(by_name[dep_name]), m["manifest"])
                    break
        parent = m.get("parent") or {}
        if parent.get("artifact") == "spring-boot-starter-parent":
            add(
                "Spring Boot",
                "Backend framework",
                parent.get("version"),
                m["manifest"] + " (parent)",
            )
        for plugin in m.get("plugins") or []:
            if plugin["id"] == "org.springframework.boot":
                add(
                    "Spring Boot",
                    "Backend framework",
                    plugin.get("version"),
                    m["manifest"] + " (plugin)",
                )
        runtime = m.get("runtime") or {}
        if eco.startswith("Dart"):
            is_flutter = "flutter" in repo.read(m["manifest"])
            flutter_version = None
            for f in (".fvmrc", ".fvm/fvm_config.json"):
                if repo.root.joinpath(f).exists():
                    try:
                        cfg = json.loads(repo.root.joinpath(f).read_text())
                        flutter_version = cfg.get("flutter") or cfg.get("flutterSdkVersion")
                    except (OSError, json.JSONDecodeError):
                        pass
            if is_flutter:
                add(
                    "Flutter",
                    "Mobile framework",
                    flutter_version or runtime.get("flutter_sdk_locked"),
                    ".fvmrc" if flutter_version else m["manifest"],
                )
            add("Dart SDK", "Language", runtime.get("dart_sdk"), m["manifest"])
        if runtime.get("php"):
            add("PHP", "Language", runtime["php"], m["manifest"])
        if runtime.get("java"):
            add("Java", "Language", runtime["java"], m["manifest"])
        if runtime.get("node"):
            add("Node.js", "Runtime", runtime["node"], m["manifest"])
        if runtime.get("go"):
            add("Go", "Language", runtime["go"], m["manifest"])
        if runtime.get("python"):
            add("Python", "Language", str(runtime["python"]), m["manifest"])

    # Frameworks detectable only from files.
    for path in repo.glob("*system/core/CodeIgniter.php"):
        v = re.search(r"define\(\s*'CI_VERSION'\s*,\s*'([^']+)'", repo.read(path))
        add("CodeIgniter 3", "Backend framework", v and v.group(1), path)
    for path in repo.glob("*system/CodeIgniter.php"):
        v = re.search(r"CI_VERSION\s*=\s*'([^']+)'", repo.read(path))
        add("CodeIgniter 4", "Backend framework", v and v.group(1), path)
    # CodeIgniter 4 app without vendor/ checked in: detect from its layout, read the version if vendor exists on disk.
    if (
        "CodeIgniter 4" not in found
        and repo.exists("spark")
        and repo.exists("app/Config/Routes.php")
    ):
        version, source = None, "spark + app/Config/Routes.php"
        core = repo.root / "vendor/codeigniter4/framework/system/CodeIgniter.php"
        if core.exists():
            v = re.search(r"CI_VERSION\s*=\s*'([^']+)'", core.read_text(errors="ignore"))
            version, source = (v.group(1) if v else None), "vendor/codeigniter4/framework"
        else:
            source += t(
                " (exact version unknown: no vendor/ folder)",
                " (versi pasti tidak diketahui: vendor/ tidak ada)",
            )
        add("CodeIgniter 4", "Backend framework", version, source)
    if "CodeIgniter 3" not in found and repo.exists("application/config/routes.php"):
        add(
            "CodeIgniter 3",
            "Backend framework",
            None,
            "application/config/routes.php"
            + t(" (no system/ folder)", " (folder system/ tidak ada)"),
        )
    if "Laravel" not in found and repo.exists("artisan") and repo.exists("routes/web.php"):
        add("Laravel", "Backend framework", None, "artisan + routes/web.php")
    if repo.exists(".nvmrc"):
        add("Node.js", "Runtime", repo.read(".nvmrc").strip(), ".nvmrc")
    return sorted(found.values(), key=lambda f: (f["category"], f["name"]))


def mobile_platforms(repo: Repo) -> dict:
    result = {}
    for gradle in ("android/app/build.gradle", "android/app/build.gradle.kts"):
        if repo.exists(gradle):
            text = repo.read(gradle)

            def grab(key):
                m = re.search(rf"{key}\s*[= ]\s*['\"]?([\w.]+)['\"]?", text)
                return m.group(1) if m else None

            flavors = []
            start = re.search(r"productFlavors\s*\{", text)
            if start:
                depth, i = 1, start.end()
                names = []
                while i < len(text) and depth:
                    if text[i] == "{":
                        if depth == 1:
                            head = text[text.rfind("\n", 0, i) + 1 : i]
                            n = re.search(r"(?:create\(\")?(\w+)\"?\)?\s*$", head)
                            if n:
                                names.append(n.group(1))
                        depth += 1
                    elif text[i] == "}":
                        depth -= 1
                    i += 1
                flavors = names
            result["android"] = {
                "file": gradle,
                "application_id": grab("applicationId"),
                "min_sdk": grab("minSdk(?:Version)?"),
                "target_sdk": grab("targetSdk(?:Version)?"),
                "compile_sdk": grab("compileSdk(?:Version)?"),
                "flavors": flavors,
                "jvm_target": grab("jvmTarget"),
            }
    pbx = "ios/Runner.xcodeproj/project.pbxproj"
    if repo.exists(pbx):
        text = repo.read(pbx)
        targets = sorted(
            set(re.findall(r"IPHONEOS_DEPLOYMENT_TARGET = ([\d.]+);", text)),
            key=lambda v: [int(x) for x in v.split(".")],
        )
        bundles = sorted(
            set(
                b
                for b in re.findall(r"PRODUCT_BUNDLE_IDENTIFIER = ([^;]+);", text)
                if "Tests" not in b
            )
        )
        podfile = re.search(r"platform\s*:ios,\s*'([\d.]+)'", repo.read("ios/Podfile"))
        result["ios"] = {
            "file": pbx,
            "deployment_target": targets[-1] if targets else None,
            "podfile_platform": podfile.group(1) if podfile else None,
            "bundle_ids": bundles,
        }
    for platform in ("web", "macos", "windows", "linux"):
        if any(f.startswith(platform + "/") for f in repo.files) and repo.exists("pubspec.yaml"):
            result.setdefault("other", []).append(platform)
    return result


def infrastructure(repo: Repo) -> dict:
    dockerfiles = []
    for path in repo.glob("Dockerfile", "*/Dockerfile", "*.Dockerfile", "Dockerfile.*"):
        images = re.findall(r"^FROM\s+(\S+)", repo.read(path), re.M | re.I)
        dockerfiles.append({"file": path, "base_images": images})
    compose = []
    for path in repo.by_name(
        "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"
    ):
        try:
            data = yaml.safe_load(repo.read(path)) or {}
        except yaml.YAMLError:
            continue
        for name, svc in (data.get("services") or {}).items():
            svc = svc or {}
            compose.append(
                {
                    "file": path,
                    "service": name,
                    "image": svc.get("image") or ("build" if svc.get("build") else None),
                    "ports": [str(p) for p in svc.get("ports") or []],
                }
            )
    ci = []
    for path in repo.glob(".github/workflows/*.yml", ".github/workflows/*.yaml"):
        try:
            data = yaml.safe_load(repo.read(path)) or {}
        except yaml.YAMLError:
            data = {}
        triggers = data.get(True) or data.get("on") or {}
        trig = (
            list(triggers.keys())
            if isinstance(triggers, dict)
            else ([triggers] if isinstance(triggers, str) else list(triggers))
        )
        ci.append(
            {
                "system": "GitHub Actions",
                "file": path,
                "name": data.get("name"),
                "triggers": [str(t) for t in trig],
            }
        )
    for name, system in (
        (".gitlab-ci.yml", "GitLab CI"),
        ("Jenkinsfile", "Jenkins"),
        ("bitbucket-pipelines.yml", "Bitbucket Pipelines"),
        ("azure-pipelines.yml", "Azure Pipelines"),
        (".circleci/config.yml", "CircleCI"),
        ("codemagic.yaml", "Codemagic"),
    ):
        if repo.exists(name):
            ci.append({"system": system, "file": name, "name": None, "triggers": []})
    return {"dockerfiles": dockerfiles, "compose_services": compose, "ci": ci}
