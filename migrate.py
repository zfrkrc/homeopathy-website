import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from app.models import init_db, create_post, slugify

POSTS = [
    {
        "file": "post-1.html",
        "title": "Homeopati ve Bilim: Ön Yargıları Yıkan Kanıtlar",
        "category": "Bilim & Kanıtlar",
        "date": "2026-07-15",
        "excerpt": '"İçinde hiçbir şey yok" efsanesini nanopartikül araştırmaları, 825.000 hastalık EPI3 çalışması ve plasebo etkisi olmayan tarım modelleriyle çürütüyoruz.'
    },
    {
        "file": "post-2.html",
        "title": "Kronik ve Genetik Durumlarda Homeopati: Bizim Hikayemiz",
        "category": "Kronik Sağlık",
        "date": "2026-07-08",
        "excerpt": "5 yıllık aile deneyimimizden yola çıkarak; migren, alerji, anksiyete ve genetik yatkınlıkların homeopatik tedavisinde vaka örnekleri ve reçeteler."
    },
    {
        "file": "post-3.html",
        "title": "Çocuklarda Homeopati: Minik Bedenler, Büyük Dönüşümler",
        "category": "Çocuk Sağlığı",
        "date": "2026-06-25",
        "excerpt": "Otizm spektrumunda dil gelişimi, hiperaktivitede denge, tekrarlayan enfeksiyonlarda bağışıklık güçlenmesi — çocuk vakalarından ilham veren sonuçlar."
    },
    {
        "file": "post-4.html",
        "title": "Duygusal Dalgalanmalardan Dengeye: Ruhsal Şikayetlerde Homeopati",
        "category": "Duygusal Sağlık",
        "date": "2026-06-18",
        "excerpt": "Yas, kaygı, öfke, tükenmişlik — homeopatinin 'benzer benzeri iyileştirir' prensibiyle ruhsal durumların dönüşümü ve kişiye özel reçete yaklaşımı."
    },
    {
        "file": "post-5.html",
        "title": "Adım Adım Homeopati: İlk Muayeneden Uzun Vadeli Takibe",
        "category": "Kronik Sağlık",
        "date": "2026-06-10",
        "excerpt": "İlk seanstan itibaren nasıl bir süreç sizi bekliyor? Sorular ve aşamalar — homeopatiye başlamadan önce bilmeniz gereken her şey."
    },
    {
        "file": "post-6.html",
        "title": "Bir Dokunuşun Gücü: Homeopatinin Bitkiler ve Hayvanlar Üzerindeki Şaşırtıcı Etkisi",
        "category": "Bilim & Kanıtlar",
        "date": "2026-06-03",
        "excerpt": "Homeopatinin sadece insanlarda değil, bitkilerde çimlenme ve verim artışı, hayvanlarda ise davranışsal iyileşmeler üzerindeki kanıtlanmış etkileri."
    }
]

if __name__ == '__main__':
    init_db()
    for p in POSTS:
        slug = slugify(p['title'])
        try:
            with open(os.path.join('src', p['file']), 'r') as f:
                content = f.read()
        except FileNotFoundError:
            print(f'⚠ {p["file"]} bulunamadı, boş içerik eklenecek.')
            content = f'<h1>{p["title"]}</h1>\n\n<p>İçerik hazırlanıyor...</p>'
        create_post(p['title'], slug, p['category'], content, p['excerpt'], 1)
        print(f'✅ {p["title"]}')
    print(f'\nToplam {len(POSTS)} yazı içe aktarıldı.')
