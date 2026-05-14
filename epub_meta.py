"""EPUB 元数据提取 - 仅使用标准库

从 EPUB 文件的 OPF 元数据中解析出书名、作者、出版社、ISBN、语言、出版日期、
描述以及封面图片。EPUB 规范:
- META-INF/container.xml 指向 OPF 文件
- OPF 的 <metadata> 用 Dublin Core (dc:*) 命名空间承载元信息
- 封面图片在 <manifest> 中定义,由 <meta name="cover" content="<id>"> 或
  EPUB 3 的 properties="cover-image" 指定
"""
from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, Optional, Union

DC_NS = "http://purl.org/dc/elements/1.1/"
OPF_NS = "http://www.idpf.org/2007/opf"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"


def extract_epub_metadata(src: Union[str, "BinaryIO"]) -> Dict[str, Any]:
    """从 EPUB 提取元数据。

    ``src`` 可以是文件路径字符串,或任何 zipfile 可接受的类文件对象。

    返回字典字段:
      title, author, publisher, isbn, language, date, description  -> str
      cover_image_bytes -> Optional[bytes]
      cover_mime        -> Optional[str]
    任意字段失败都返回空串 / None,不抛异常。
    """
    result: Dict[str, Any] = {
        "title": "",
        "author": "",
        "publisher": "",
        "isbn": "",
        "language": "",
        "date": "",
        "description": "",
        "cover_image_bytes": None,
        "cover_mime": None,
    }

    try:
        with zipfile.ZipFile(src) as zf:
            opf_path = _find_opf_path(zf)
            if not opf_path:
                return result

            try:
                opf_data = zf.read(opf_path)
            except KeyError:
                return result

            try:
                opf_root = ET.fromstring(opf_data)
            except ET.ParseError:
                return result

            metadata = _find_with_fallback(opf_root, "metadata", OPF_NS)
            if metadata is None:
                return result

            result["title"] = _first_text(metadata, "title", DC_NS)
            result["author"] = _collect_creators(metadata)
            result["publisher"] = _first_text(metadata, "publisher", DC_NS)
            result["language"] = _first_text(metadata, "language", DC_NS)
            result["date"] = _extract_date(metadata)
            result["description"] = _clean_html(
                _first_text(metadata, "description", DC_NS)
            )
            result["isbn"] = _extract_isbn(metadata)

            cover_bytes, cover_mime = _extract_cover(zf, opf_root, opf_path)
            result["cover_image_bytes"] = cover_bytes
            result["cover_mime"] = cover_mime

    except (zipfile.BadZipFile, OSError):
        # 损坏的 epub / 读不到文件:返回空字典结构
        return result

    return result


# ---------- 内部辅助 ----------

def _find_opf_path(zf: zipfile.ZipFile) -> Optional[str]:
    """通过 META-INF/container.xml 找 OPF 相对路径"""
    try:
        data = zf.read("META-INF/container.xml")
    except KeyError:
        return None
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    rootfile = _find_with_fallback(root, "rootfile", CONTAINER_NS, recursive=True)
    if rootfile is None:
        return None
    return rootfile.attrib.get("full-path")


def _find_with_fallback(parent, tag: str, ns: str, recursive: bool = False):
    """先按命名空间查,查不到再无命名空间兜底。"""
    qname = f"{{{ns}}}{tag}"
    if recursive:
        elem = parent.find(f".//{qname}")
        if elem is None:
            elem = parent.find(f".//{tag}")
    else:
        elem = parent.find(qname)
        if elem is None:
            elem = parent.find(tag)
    return elem


def _findall_with_fallback(parent, tag: str, ns: str):
    qname = f"{{{ns}}}{tag}"
    items = parent.findall(qname)
    if not items:
        items = parent.findall(tag)
    return items


def _first_text(metadata, tag: str, ns: str) -> str:
    elem = _find_with_fallback(metadata, tag, ns)
    if elem is None or elem.text is None:
        return ""
    return elem.text.strip()


def _collect_creators(metadata) -> str:
    creators = _findall_with_fallback(metadata, "creator", DC_NS)
    names = []
    for c in creators:
        if c.text:
            t = c.text.strip()
            if t and t not in names:
                names.append(t)
    return "、".join(names)


def _extract_date(metadata) -> str:
    """返回 YYYY-MM-DD(若可解析),否则原样返回第一个 date 字段的前 10 字符"""
    raw = _first_text(metadata, "date", DC_NS)
    if not raw:
        return ""
    # 很多 epub 的 date 是完整 ISO 时间,或只是年份
    m = re.match(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", raw)
    if m:
        y, mo, d = m.group(1), m.group(2) or "01", m.group(3) or "01"
        return f"{y}-{mo}-{d}"
    return raw[:10]


def _extract_isbn(metadata) -> str:
    idents = _findall_with_fallback(metadata, "identifier", DC_NS)
    scheme_attr_opf = f"{{{OPF_NS}}}scheme"
    fallback = ""
    for ident in idents:
        text = (ident.text or "").strip() if ident.text else ""
        if not text:
            continue
        scheme = (ident.attrib.get(scheme_attr_opf) or ident.attrib.get("scheme") or "").lower()
        if "isbn" in scheme or "isbn" in text.lower():
            return _normalize_isbn(text)
        if not fallback and _looks_like_isbn(text):
            fallback = _normalize_isbn(text)
    return fallback


def _looks_like_isbn(s: str) -> bool:
    digits = re.sub(r"[^0-9Xx]", "", s)
    return len(digits) in (10, 13)


def _normalize_isbn(s: str) -> str:
    """保留数字和 X,去掉其他字符"""
    return re.sub(r"[^0-9Xx]", "", s).upper()


def _clean_html(s: str) -> str:
    """EPUB 的 description 可能带 HTML 标签,粗略清洗"""
    if not s:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def _extract_cover(zf: zipfile.ZipFile, opf_root, opf_path: str):
    """返回 (bytes, mime) 或 (None, None)"""
    manifest = _find_with_fallback(opf_root, "manifest", OPF_NS)
    metadata = _find_with_fallback(opf_root, "metadata", OPF_NS)
    if manifest is None:
        return None, None

    items = _findall_with_fallback(manifest, "item", OPF_NS)
    items_by_id = {it.attrib.get("id"): it for it in items if it.attrib.get("id")}

    href = None
    mime = None

    # 1) EPUB 2 风格: <meta name="cover" content="<item-id>">
    if metadata is not None:
        for meta_elem in _findall_with_fallback(metadata, "meta", OPF_NS):
            if meta_elem.attrib.get("name", "").lower() == "cover":
                cid = meta_elem.attrib.get("content")
                it = items_by_id.get(cid)
                if it is not None:
                    href = it.attrib.get("href")
                    mime = it.attrib.get("media-type")
                break

    # 2) EPUB 3 风格: manifest item 带 properties="cover-image"
    if href is None:
        for it in items:
            props = it.attrib.get("properties", "")
            if "cover-image" in props:
                href = it.attrib.get("href")
                mime = it.attrib.get("media-type")
                break

    # 3) 兜底: 文件名含 cover 的图片资源
    if href is None:
        for it in items:
            h = it.attrib.get("href", "")
            m = it.attrib.get("media-type", "")
            if "cover" in h.lower() and m.startswith("image/"):
                href = h
                mime = m
                break

    if not href:
        return None, None

    # 相对 OPF 所在目录解析
    opf_dir = posixpath.dirname(opf_path)
    full_path = posixpath.normpath(posixpath.join(opf_dir, href)) if opf_dir else href
    try:
        data = zf.read(full_path)
    except KeyError:
        return None, None

    if not mime:
        mime = _guess_image_mime(full_path)
    return data, mime


def _guess_image_mime(path: str) -> str:
    p = path.lower()
    if p.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if p.endswith(".png"):
        return "image/png"
    if p.endswith(".gif"):
        return "image/gif"
    if p.endswith(".webp"):
        return "image/webp"
    return "application/octet-stream"


def cover_ext_from_mime(mime: Optional[str]) -> str:
    """根据 mime 返回合适后缀(用于保存)"""
    if not mime:
        return "bin"
    m = mime.lower()
    if "jpeg" in m or "jpg" in m:
        return "jpg"
    if "png" in m:
        return "png"
    if "gif" in m:
        return "gif"
    if "webp" in m:
        return "webp"
    return "bin"
