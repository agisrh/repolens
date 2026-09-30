"""Frameworks, libraries, and language runtimes, with the version of each and where it came from.

Most come from the dependency manifests via FRAMEWORK_RULES; a few (CodeIgniter, Laravel
without a lock file, Flutter pinned by FVM) are recognised from files instead. To recognise
another framework from its package, add a row to FRAMEWORK_RULES.
"""

from __future__ import annotations

import json
import re

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


RUNTIMES = [  # manifest runtime key -> (name, category)
    ("php", "PHP", "Language"),
    ("java", "Java", "Language"),
    ("node", "Node.js", "Runtime"),
    ("go", "Go", "Language"),
    ("python", "Python", "Language"),
]


class _Found(dict):
    """name -> framework entry. A later source only replaces an entry that had no version."""

    def add(self, name: str, category: str, version, source: str) -> None:
        if name not in self or (version and not self[name]["version"]):
            self[name] = {"name": name, "category": category, "version": version, "source": source}


def frameworks(repo: Repo, manifests: list[dict]) -> list[dict]:
    """Sorted by category, then name."""
    found = _Found()
    for manifest in manifests:
        _from_dependencies(found, manifest)
        _spring_boot(found, manifest)
        if manifest["ecosystem"].startswith("Dart"):
            _flutter(found, repo, manifest)
        _runtimes(found, manifest)
    _from_files(found, repo)
    return sorted(found.values(), key=lambda f: (f["category"], f["name"]))


def _from_dependencies(found: _Found, manifest: dict) -> None:
    """Every FRAMEWORK_RULES entry whose package is a dependency of this manifest."""
    packages = {d["name"]: d for d in manifest["dependencies"]}
    for name, category, prefix, package_names in FRAMEWORK_RULES:
        if not manifest["ecosystem"].startswith(prefix):
            continue
        package = next((packages[p] for p in package_names if p in packages), None)
        if package:
            version = package.get("resolved") or package.get("declared")
            found.add(name, category, version, manifest["manifest"])


def _spring_boot(found: _Found, manifest: dict) -> None:
    """Spring Boot as the Maven parent or the Gradle plugin (not only as a dependency)."""
    parent = manifest.get("parent") or {}
    if parent.get("artifact") == "spring-boot-starter-parent":
        source = manifest["manifest"] + " (parent)"
        found.add("Spring Boot", "Backend framework", parent.get("version"), source)
    for plugin in manifest.get("plugins") or []:
        if plugin["id"] == "org.springframework.boot":
            source = manifest["manifest"] + " (plugin)"
            found.add("Spring Boot", "Backend framework", plugin.get("version"), source)


def _flutter(found: _Found, repo: Repo, manifest: dict) -> None:
    """Flutter (the version pinned by FVM, else the one in pubspec.lock) and the Dart SDK."""
    runtime = manifest.get("runtime") or {}
    pinned = None
    for name in (".fvmrc", ".fvm/fvm_config.json"):
        if repo.root.joinpath(name).exists():
            try:
                config = json.loads(repo.root.joinpath(name).read_text())
                pinned = config.get("flutter") or config.get("flutterSdkVersion")
            except (OSError, json.JSONDecodeError):
                pass
    if "flutter" in repo.read(manifest["manifest"]):
        version = pinned or runtime.get("flutter_sdk_locked")
        source = ".fvmrc" if pinned else manifest["manifest"]
        found.add("Flutter", "Mobile framework", version, source)
    found.add("Dart SDK", "Language", runtime.get("dart_sdk"), manifest["manifest"])


def _runtimes(found: _Found, manifest: dict) -> None:
    runtime = manifest.get("runtime") or {}
    for key, name, category in RUNTIMES:
        if runtime.get(key):
            version = str(runtime[key]) if key == "python" else runtime[key]
            found.add(name, category, version, manifest["manifest"])


def _from_files(found: _Found, repo: Repo) -> None:
    """Frameworks recognised from their files, for projects without (complete) manifests."""
    for path in repo.glob("*system/core/CodeIgniter.php"):
        version = re.search(r"define\(\s*'CI_VERSION'\s*,\s*'([^']+)'", repo.read(path))
        found.add("CodeIgniter 3", "Backend framework", version and version.group(1), path)
    for path in repo.glob("*system/CodeIgniter.php"):
        version = re.search(r"CI_VERSION\s*=\s*'([^']+)'", repo.read(path))
        found.add("CodeIgniter 4", "Backend framework", version and version.group(1), path)
    if (
        "CodeIgniter 4" not in found
        and repo.exists("spark")
        and repo.exists("app/Config/Routes.php")
    ):
        found.add("CodeIgniter 4", "Backend framework", *_codeigniter4_without_vendor(repo))
    if "CodeIgniter 3" not in found and repo.exists("application/config/routes.php"):
        source = "application/config/routes.php" + t(
            " (no system/ folder)", " (folder system/ tidak ada)"
        )
        found.add("CodeIgniter 3", "Backend framework", None, source)
    if "Laravel" not in found and repo.exists("artisan") and repo.exists("routes/web.php"):
        found.add("Laravel", "Backend framework", None, "artisan + routes/web.php")
    if repo.exists(".nvmrc"):
        found.add("Node.js", "Runtime", repo.read(".nvmrc").strip(), ".nvmrc")


def _codeigniter4_without_vendor(repo: Repo) -> tuple[str | None, str]:
    """(version, source) for a CodeIgniter 4 app whose vendor/ is not committed: the version
    is read from vendor/ when it exists on disk, and is unknown otherwise."""
    core = repo.root / "vendor/codeigniter4/framework/system/CodeIgniter.php"
    if core.exists():
        version = re.search(r"CI_VERSION\s*=\s*'([^']+)'", core.read_text(errors="ignore"))
        return (version.group(1) if version else None), "vendor/codeigniter4/framework"
    unknown = t(
        " (exact version unknown: no vendor/ folder)",
        " (versi pasti tidak diketahui: vendor/ tidak ada)",
    )
    return None, "spark + app/Config/Routes.php" + unknown
