<?php
namespace App\Models;
use CodeIgniter\Model;
class Berita_model extends Model
{
    protected $table = 'cp_berita';
    protected $primaryKey = 'id_berita';
    protected $kip_table = 'cp_kip';

    public function listing()
    {
        $sql = $this->db->table($this->table . ' berita');
        $sql->select('berita.*, kategori.nama_kategori, users.nama');
        $sql->join('kategori', 'kategori.id_kategori = berita.id_kategori', 'LEFT');
        $sql->join('users', 'users.id_user = berita.id_user', 'LEFT');
        $sql->where(['berita.status_berita' => 'Publish']);
        $sql->orderBy('berita.tanggal_publish', 'DESC');
        return $sql->get()->getResultArray();
    }

    public function kip()
    {
        $sql = $this->db->table($this->kip_table);
        $sql->where('is_active', 1);
        return $sql->get()->getResultArray();
    }
}
